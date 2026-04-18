/*cluade optimised version*/
#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif

#include <iostream>
#include <fstream>
#include <vector>
#include <unordered_map>
#include <unordered_set>
#include <queue>
#include <cmath>
#include <fcntl.h>
#include <unistd.h>
#include <cstdlib>
#include <chrono>
#include <iomanip>
#include <immintrin.h>
#include <liburing.h>
#include <cstring>
#include <limits>
#include "json.hpp"

// g++ benchmark_search.cpp -o benchmark_search -O3 -march=native -luring -std=c++17

using json = nlohmann::json;

struct VectorRecord {
    uint64_t bitmask[2];   // 16 bytes  @ offset 0
    int8_t   vector[128];  // 128 bytes @ offset 16
    uint32_t id;           // 4 bytes   @ offset 144
    uint8_t  padding[12];  // 12 bytes  @ offset 148 -> total = 160
};
static_assert(sizeof(VectorRecord) == 160, "VectorRecord must be exactly 160 bytes");
static_assert(offsetof(VectorRecord, vector) % 16 == 0, "vector must be 16-byte aligned");

struct ClusterInfo {
    size_t   num_vectors;
    size_t   byte_offset;
    size_t   length_bytes;
    float*   scale;
    float*   zero_point;
};

inline float hsum256_ps(__m256 v) {
    __m128 lo   = _mm256_castps256_ps128(v);
    __m128 hi   = _mm256_extractf128_ps(v, 1);
    __m128 sum  = _mm_add_ps(lo, hi);
    __m128 shuf = _mm_movehdup_ps(sum);
    sum  = _mm_add_ps(sum, shuf);
    shuf = _mm_movehl_ps(shuf, sum);
    sum  = _mm_add_ss(sum, shuf);
    return _mm_cvtss_f32(sum);
}

inline float l2_distance_simd_int8_asymmetric(
    const float*  query,
    const int8_t* db_vector,
    const float*  scale,
    const float*  zero_point)
{
    __m256 sum_vec = _mm256_setzero_ps();
    for (int i = 0; i < 128; i += 8) {
        __m256 q = _mm256_loadu_ps(&query[i]);
        int8_t tmp[8];
        std::memcpy(tmp, &db_vector[i], 8);
        __m128i db_int8  = _mm_loadl_epi64(reinterpret_cast<const __m128i*>(tmp));
        __m256i db_int32 = _mm256_cvtepi8_epi32(db_int8);
        __m256  db_float = _mm256_cvtepi32_ps(db_int32);
        __m256  zp       = _mm256_loadu_ps(&zero_point[i]);
        __m256  sc       = _mm256_loadu_ps(&scale[i]);
        db_float = _mm256_sub_ps(db_float, zp);
        db_float = _mm256_mul_ps(db_float, sc);
        __m256 diff = _mm256_sub_ps(q, db_float);
        sum_vec = _mm256_fmadd_ps(diff, diff, sum_vec);
    }
    return hsum256_ps(sum_vec);
}

inline float l2_distance_float_simd(const float* a, const float* b) {
    __m256 sum_vec = _mm256_setzero_ps();
    for (int i = 0; i < 128; i += 8) {
        __m256 va   = _mm256_loadu_ps(&a[i]);
        __m256 vb   = _mm256_loadu_ps(&b[i]);
        __m256 diff = _mm256_sub_ps(va, vb);
        sum_vec = _mm256_fmadd_ps(diff, diff, sum_vec);
    }
    return hsum256_ps(sum_vec);
}

inline float l2_partial_16d(
    const float*  query,
    const int8_t* db_vector,
    const float*  scale,
    const float*  zero_point)
{
    __m256 sum_vec = _mm256_setzero_ps();
    for (int i = 0; i < 16; i += 8) {
        __m256 q = _mm256_loadu_ps(&query[i]);
        int8_t tmp[8];
        std::memcpy(tmp, &db_vector[i], 8);
        __m128i db_int8  = _mm_loadl_epi64(reinterpret_cast<const __m128i*>(tmp));
        __m256i db_int32 = _mm256_cvtepi8_epi32(db_int8);
        __m256  db_float = _mm256_cvtepi32_ps(db_int32);
        __m256  zp       = _mm256_loadu_ps(&zero_point[i]);
        __m256  sc       = _mm256_loadu_ps(&scale[i]);
        db_float = _mm256_sub_ps(db_float, zp);
        db_float = _mm256_mul_ps(db_float, sc);
        __m256 diff = _mm256_sub_ps(q, db_float);
        sum_vec = _mm256_fmadd_ps(diff, diff, sum_vec);
    }
    return hsum256_ps(sum_vec);
}

// ============================================================
// Process one completed cluster slot — called from the drain
// loop below. Separated into a function for clarity.
// ============================================================
static void process_cluster(
    int                  slot,
    const ClusterInfo*   info,
    char*                buffer_pool,
    size_t               max_cluster_bytes,
    const float*         current_query,
    const uint64_t*      q_mask,
    int                  bitmask_threshold,
    std::priority_queue<std::pair<float,uint32_t>>& top_k,
    float&               heap_worst,
    long long&           simd_avoided,
    float*               local_scale,   // caller-provided L1 scratch
    float*               local_zp)
{
    const VectorRecord* records = reinterpret_cast<const VectorRecord*>(
        buffer_pool + (slot * max_cluster_bytes));

    // Copy 256 floats from flat_quant_params into L1-resident stack buffers.
    // Pays ~4 AVX2 ops once; saves L3 pointer-chase on every vector below.
    std::memcpy(local_scale, info->scale,      128 * sizeof(float));
    std::memcpy(local_zp,    info->zero_point, 128 * sizeof(float));

    for (size_t v = 0; v < info->num_vectors; ++v) {
        // Layer 1: Hamming bitmask (~1 clock)
        int hd = __builtin_popcountll(q_mask[0] ^ records[v].bitmask[0]) +
                 __builtin_popcountll(q_mask[1] ^ records[v].bitmask[1]);
        if (hd > bitmask_threshold) { simd_avoided++; continue; }

        // Layer 2: 16D partial lower bound (once heap is full)
        if ((int)top_k.size() >= 10) {
            float p = l2_partial_16d(current_query, records[v].vector,
                                     local_scale, local_zp);
            if (p >= heap_worst) { simd_avoided++; continue; }
        }

        // Layer 3: Full 128D AVX2 distance
        float dist = l2_distance_simd_int8_asymmetric(
            current_query, records[v].vector, local_scale, local_zp);

        if ((int)top_k.size() < 10) {
            top_k.push({dist, records[v].id});
            if ((int)top_k.size() == 10)
                heap_worst = top_k.top().first;
        } else if (dist < heap_worst) {
            top_k.pop();
            top_k.push({dist, records[v].id});
            heap_worst = top_k.top().first;
        }
    }
}

int main(int argc, char* argv[]) {
    bool use_direct = true;
    bool no_warmup  = false;
    int  probes     = 100;

    for (int i = 1; i < argc; ++i) {
        std::string arg = argv[i];
        if (arg == "--cache") {
            use_direct = false;
        } else if (arg == "--no-warmup") {
            no_warmup = true;
        } else if (arg == "--probes" && i + 1 < argc) {
            probes = std::stoi(argv[++i]);
            if (probes < 1 || probes > 256) {
                std::cerr << "[!] --probes must be 1..256 (io_uring queue depth limit)\n";
                return 1;
            }
        }
    }

    if (use_direct)
        std::cout << "[*] Initializing TapeANN Benchmark (10M SIFT / io_uring Async O_DIRECT)...\n";
    else
        std::cout << "[*] Initializing TapeANN Benchmark (10M SIFT / io_uring Page Cache)...\n";

    std::vector<float> centroids(10000 * 128);
    {
        std::ifstream f("centroids.bin", std::ios::binary);
        if (!f) { std::cerr << "[!] Cannot open centroids.bin\n"; return 1; }
        f.read(reinterpret_cast<char*>(centroids.data()), centroids.size() * sizeof(float));
    }

    std::vector<float> global_mean(128);
    {
        std::ifstream f("global_mean.bin", std::ios::binary);
        if (!f) { std::cerr << "[!] Cannot open global_mean.bin\n"; return 1; }
        f.read(reinterpret_cast<char*>(global_mean.data()), 128 * sizeof(float));
    }

    std::ifstream json_file("segment_table.json");
    if (!json_file) { std::cerr << "[!] Cannot open segment_table.json\n"; return 1; }
    json j = json::parse(json_file);

    std::unordered_map<int, ClusterInfo> segment_table;
    segment_table.reserve(10000);
    std::vector<float> flat_quant_params(10000 * 256, 0.0f);
    size_t max_cluster_bytes = 0;

    for (auto& [key, val] : j.items()) {
        int cid = std::stoi(key);
        ClusterInfo info;
        info.num_vectors  = val["num_vectors"].get<size_t>();
        info.byte_offset  = val["byte_offset"].get<size_t>();
        info.length_bytes = val["length_bytes"].get<size_t>();
        info.scale        = &flat_quant_params[cid * 256];
        info.zero_point   = &flat_quant_params[cid * 256 + 128];
        auto spd = val["scale_per_dim"].get<std::vector<float>>();
        auto zpd = val["zp_per_dim"].get<std::vector<float>>();
        std::copy(spd.begin(), spd.end(), info.scale);
        std::copy(zpd.begin(), zpd.end(), info.zero_point);
        if (info.length_bytes > max_cluster_bytes)
            max_cluster_bytes = info.length_bytes;
        segment_table[cid] = info;
    }

    const int num_queries = 10000;
    std::vector<float> test_queries(num_queries * 128);
    {
        std::ifstream f("test_queries.bin", std::ios::binary);
        if (!f) { std::cerr << "[!] Cannot open test_queries.bin\n"; return 1; }
        f.read(reinterpret_cast<char*>(test_queries.data()), test_queries.size() * sizeof(float));
    }
    std::vector<uint32_t> ground_truth(num_queries * 10);
    {
        std::ifstream f("ground_truth.bin", std::ios::binary);
        if (!f) { std::cerr << "[!] Cannot open ground_truth.bin\n"; return 1; }
        f.read(reinterpret_cast<char*>(ground_truth.data()), ground_truth.size() * sizeof(uint32_t));
    }

    int open_flags = O_RDONLY;
    if (use_direct) open_flags |= O_DIRECT;
    int tape_fd = open("index_tape.bin", open_flags);
    if (tape_fd < 0) { std::cerr << "[!] Failed to open index_tape.bin\n"; return 1; }

    void* aligned_master_buffer = nullptr;
    if (posix_memalign(&aligned_master_buffer, 4096, max_cluster_bytes * probes) != 0) {
        std::cerr << "[!] posix_memalign failed\n"; return 1;
    }
    char* buffer_pool = static_cast<char*>(aligned_master_buffer);

    // ============================================================
    // io_uring: IORING_SETUP_SQPOLL enables kernel-side submission
    // polling — the kernel thread spins on the SQ, so submit()
    // requires zero syscalls when the SQ thread is awake.
    // This eliminates the 64s of system time from 800k syscalls.
    //
    // IORING_SETUP_SQPOLL requires either CAP_SYS_ADMIN or
    // /proc/sys/kernel/io_uring_sqpoll_cpu to be set, OR the
    // process runs as root. If init fails, we fall back to the
    // standard ring (which still batches completions better than
    // the old one-at-a-time wait loop).
    // ============================================================
    struct io_uring ring;
    struct io_uring_params params = {};
    params.flags = IORING_SETUP_SQPOLL;
    params.sq_thread_idle = 2000; // kernel SQ thread idles for 2s before sleeping

    bool sqpoll_active = false;
    if (io_uring_queue_init_params(256, &ring, &params) == 0) {
        sqpoll_active = true;
        std::cout << "[+] io_uring SQPOLL active — zero-syscall submission enabled.\n";
    } else {
        // Fallback: standard ring, still uses batched CQE draining
        if (io_uring_queue_init(256, &ring, 0) < 0) {
            std::cerr << "[!] Failed to initialize io_uring\n"; return 1;
        }
        std::cout << "[+] io_uring standard mode (SQPOLL unavailable — try sudo or CAP_SYS_ADMIN).\n";
    }
    (void)sqpoll_active;

    if (!use_direct && !no_warmup) {
        std::cout << "[*] Performing warm-up pass (1000 queries) to populate Linux Page Cache...\n";
        for (int q = 0; q < 1000; ++q) {
            const float* cq = &test_queries[q * 128];
            std::priority_queue<std::pair<float,int>> cpq;
            for (int i = 0; i < 10000; ++i) {
                float d = l2_distance_float_simd(cq, &centroids[i * 128]);
                if ((int)cpq.size() < probes) cpq.push({d, i});
                else if (d < cpq.top().first) { cpq.pop(); cpq.push({d, i}); }
            }
            for (int i = probes - 1; i >= 0; --i) {
                int cid = cpq.top().second; cpq.pop();
                auto& info = segment_table[cid];
                struct io_uring_sqe* sqe = io_uring_get_sqe(&ring);
                io_uring_prep_read(sqe, tape_fd,
                    buffer_pool + (i * max_cluster_bytes),
                    info.length_bytes, info.byte_offset);
            }
            io_uring_submit(&ring);
            for (int i = 0; i < probes; ++i) {
                struct io_uring_cqe* cqe;
                io_uring_wait_cqe(&ring, &cqe);
                io_uring_cqe_seen(&ring, cqe);
            }
        }
        std::cout << "[+] Warm-up complete. Starting timed benchmark.\n";
    }

    std::cout << "[+] io_uring initialized. Async SSD Pool Size: "
              << (max_cluster_bytes * probes / 1024 / 1024) << " MB.\n";
    std::cout << "[+] Running " << num_queries << " queries...\n\n";

    const int bitmask_threshold = 45;
    double    total_recall       = 0.0;
    double    total_recall1      = 0.0;
    double    total_latency_ms   = 0.0;
    long long total_simd_avoided = 0;
    long long total_ios          = 0;
    std::vector<double> query_latencies(num_queries);

    std::vector<ClusterInfo*> active_infos(probes);
    std::vector<int>          target_clusters(probes);

    // L1-resident scratch buffers for per-cluster quantization params
    alignas(32) float local_scale[128];
    alignas(32) float local_zp[128];

    // CQE batch drain buffer — reap up to 'probes' completions at once
    std::vector<struct io_uring_cqe*> cqe_batch(probes);

    for (int q = 0; q < num_queries; ++q) {
        const float* current_query = &test_queries[q * 128];
        auto start_time = std::chrono::high_resolution_clock::now();

        uint64_t q_mask[2] = {0, 0};
        for (int j = 0; j < 64; ++j) {
            if (current_query[j]      > global_mean[j])      q_mask[0] |= (1ULL << j);
            if (current_query[j + 64] > global_mean[j + 64]) q_mask[1] |= (1ULL << j);
        }

        std::priority_queue<std::pair<float,int>> cluster_pq;
        for (int i = 0; i < 10000; ++i) {
            float dist = l2_distance_float_simd(current_query, &centroids[i * 128]);
            if ((int)cluster_pq.size() < probes) {
                cluster_pq.push({dist, i});
            } else if (dist < cluster_pq.top().first) {
                cluster_pq.pop();
                cluster_pq.push({dist, i});
            }
        }
        for (int i = probes - 1; i >= 0; --i) {
            target_clusters[i] = cluster_pq.top().second;
            cluster_pq.pop();
        }

        for (int i = 0; i < probes; ++i) {
            active_infos[i] = &segment_table[target_clusters[i]];
            struct io_uring_sqe* sqe = io_uring_get_sqe(&ring);
            io_uring_prep_read(sqe, tape_fd,
                buffer_pool + (i * max_cluster_bytes),
                active_infos[i]->length_bytes,
                active_infos[i]->byte_offset);
            io_uring_sqe_set_data(sqe, (void*)(uintptr_t)i);
        }
        io_uring_submit(&ring);
        total_ios += probes;

        std::priority_queue<std::pair<float, uint32_t>> top_k_results;
        float heap_worst = std::numeric_limits<float>::max();

        // ============================================================
        // BATCHED CQE DRAIN: instead of waiting for one completion
        // at a time (80 separate syscalls), we wait for the first
        // completion to arrive, then peek at everything else that's
        // already ready — draining as many CQEs as possible per
        // syscall. Reduces 80 wait_cqe syscalls to typically 1-3.
        // ============================================================
        int remaining = probes;
        while (remaining > 0) {
            // Block until at least 1 CQE is ready
            struct io_uring_cqe* cqe;
            io_uring_wait_cqe(&ring, &cqe);

            // Now greedily peek at everything else already in the CQ
            // without blocking — this is a pure ring buffer read, 0 syscalls
            unsigned head;
            int batch_count = 0;
            io_uring_for_each_cqe(&ring, head, cqe) {
                cqe_batch[batch_count++] = cqe;
                if (batch_count >= remaining) break;
            }
            io_uring_cq_advance(&ring, batch_count);
            remaining -= batch_count;

            // Process all collected completions
            for (int b = 0; b < batch_count; ++b) {
                int slot = (int)(uintptr_t)io_uring_cqe_get_data(cqe_batch[b]);
                process_cluster(slot, active_infos[slot],
                    buffer_pool, max_cluster_bytes,
                    current_query, q_mask, bitmask_threshold,
                    top_k_results, heap_worst, total_simd_avoided,
                    local_scale, local_zp);
            }
        }

        auto end_time = std::chrono::high_resolution_clock::now();
        double qlatency = std::chrono::duration<double, std::milli>(end_time - start_time).count();
        total_latency_ms += qlatency;
        query_latencies[q] = qlatency;

        std::unordered_set<uint32_t> true_nn;
        for (int j = 0; j < 10; ++j)
            true_nn.insert(ground_truth[q * 10 + j]);
        uint32_t true_top1 = ground_truth[q * 10 + 0];
        // Drain heap; the max element (root) is the worst-ranked of our top-10,
        // the last element popped is the best (our predicted top-1).
        int matches = 0;
        uint32_t predicted_top1 = 0;
        while (!top_k_results.empty()) {
            if (true_nn.count(top_k_results.top().second)) matches++;
            predicted_top1 = top_k_results.top().second;
            top_k_results.pop();
        }
        total_recall  += (matches / 10.0);
        total_recall1 += (predicted_top1 == true_top1) ? 1.0 : 0.0;

        if ((q + 1) % 1000 == 0)
            std::cout << "Processed " << (q + 1) << " / " << num_queries << " queries...\n";
    }

    // Compute percentiles
    std::sort(query_latencies.begin(), query_latencies.end());
    auto percentile = [&](double p) -> double {
        int idx = static_cast<int>(p / 100.0 * num_queries);
        if (idx >= num_queries) idx = num_queries - 1;
        return query_latencies[idx];
    };
    double mean_ms     = total_latency_ms / num_queries;
    double recall_pct  = (total_recall  / num_queries) * 100.0;
    double recall1_pct = (total_recall1 / num_queries) * 100.0;
    double qps         = 1000.0 / mean_ms;
    double ios_per_q   = (double)total_ios / num_queries;
    double p50  = percentile(50);
    double p95  = percentile(95);
    double p99  = percentile(99);
    double p999 = percentile(99.9);

    std::cout << "\n=========================================\n";
    std::cout << (use_direct
        ? "        10M SCALE O_DIRECT BARE METAL      "
        : "        10M SCALE LINUX PAGE CACHE        ") << "\n";
    std::cout << "=========================================\n";
    std::cout << "Probes per query : " << probes << " clusters\n";
    std::cout << "Average Latency  : " << mean_ms << " ms\n";
    std::cout << "P50 Latency      : " << p50  << " ms\n";
    std::cout << "P95 Latency      : " << p95  << " ms\n";
    std::cout << "P99 Latency      : " << p99  << " ms\n";
    std::cout << "P99.9 Latency    : " << p999 << " ms\n";
    std::cout << "Recall@10        : " << recall_pct  << " %\n";
    std::cout << "Recall@1         : " << recall1_pct << " %\n";
    std::cout << "QPS (1 thread)   : " << qps << "\n";
    std::cout << "IOs per query    : " << ios_per_q << "\n";
    std::cout << "SIMD Calcs Saved : " << total_simd_avoided << " vectors skipped!\n";
    std::cout << "=========================================\n";

    // Machine-readable CSV line (grep for ^CSV: to extract)
    // Schema v2: algo,probes,recall10,recall1,qps,mean_ms,p50,p95,p99,p999,ios_per_q,simd_avoided
    std::cout << std::fixed << std::setprecision(4);
    std::cout << "CSV:tapeann,probes," << probes
              << "," << recall_pct
              << "," << recall1_pct
              << "," << qps
              << "," << mean_ms
              << "," << p50
              << "," << p95
              << "," << p99
              << "," << p999
              << "," << ios_per_q
              << "," << total_simd_avoided
              << "\n";

    io_uring_queue_exit(&ring);
    free(aligned_master_buffer);
    close(tape_fd);
    return 0;
}

/*old code*/
/*

#ifndef _GNU_SOURCE
#define _GNU_SOURCE 
#endif

#include <iostream>
#include <fstream>
#include <vector>
#include <unordered_map>
#include <unordered_set>
#include <queue>
#include <cmath>
#include <fcntl.h>
#include <unistd.h>
#include <cstdlib> 
#include <chrono>
#include <iomanip>
#include <immintrin.h> 
#include <liburing.h> // The Linux Asynchronous I/O Magic
#include "json.hpp" 

using json = nlohmann::json;

// g++ benchmark_search.cpp -o benchmark_search -O3 -march=native -luring

#pragma pack(push, 1)
struct VectorRecord {
    uint64_t bitmask[2];
    int8_t vector[128];
    uint32_t id;
    uint8_t padding[12]; 
};
#pragma pack(pop)

struct ClusterInfo {
    size_t num_vectors;
    size_t byte_offset;
    size_t length_bytes;
    float scale;
    float zero_point; 
};

inline float l2_distance_simd_int8_asymmetric(const float* query, const int8_t* db_vector, float scale, float zero_point) {
    __m256 sum_vec = _mm256_setzero_ps();
    __m256 scale_vec = _mm256_set1_ps(scale); 
    __m256 zp_vec = _mm256_set1_ps(zero_point); 

    for (int i = 0; i < 128; i += 8) {
        __m256 q = _mm256_loadu_ps(&query[i]);
        __m128i db_int8 = _mm_loadl_epi64(reinterpret_cast<const __m128i*>(&db_vector[i]));
        __m256i db_int32 = _mm256_cvtepi8_epi32(db_int8);
        __m256 db_float = _mm256_cvtepi32_ps(db_int32);

        db_float = _mm256_sub_ps(db_float, zp_vec);
        db_float = _mm256_mul_ps(db_float, scale_vec);

        __m256 diff = _mm256_sub_ps(q, db_float);
        sum_vec = _mm256_fmadd_ps(diff, diff, sum_vec);
    }

    float sum_array[8];
    _mm256_storeu_ps(sum_array, sum_vec);
    return sum_array[0] + sum_array[1] + sum_array[2] + sum_array[3] + 
           sum_array[4] + sum_array[5] + sum_array[6] + sum_array[7];
}

inline float l2_distance_float_simd(const float* a, const float* b) {
    __m256 sum_vec = _mm256_setzero_ps(); // Initialize 8 float accumulators to 0
    
    // Process 128 dimensions in chunks of 8
    for (int i = 0; i < 128; i += 8) {
        __m256 va = _mm256_loadu_ps(&a[i]);       // Load 8 floats from query
        __m256 vb = _mm256_loadu_ps(&b[i]);       // Load 8 floats from centroid
        __m256 diff = _mm256_sub_ps(va, vb);      // Subtract all 8 simultaneously
        sum_vec = _mm256_fmadd_ps(diff, diff, sum_vec); // Fused Multiply-Add (diff^2 + sum)
    }
    
    // Horizontally sum the 8 accumulators into a single scalar float
    float sum_array[8];
    _mm256_storeu_ps(sum_array, sum_vec);
    return sum_array[0] + sum_array[1] + sum_array[2] + sum_array[3] + 
           sum_array[4] + sum_array[5] + sum_array[6] + sum_array[7];
}

int main(int argc, char* argv[]) {
    bool use_direct = true;
    if (argc > 1 && std::string(argv[1]) == "--cache") {
        use_direct = false;
    }

    if (use_direct) {
        std::cout << "[*] Initializing TapeANN Benchmark (10M SIFT / io_uring Async O_DIRECT)..." << std::endl;
    } else {
        std::cout << "[*] Initializing TapeANN Benchmark (10M SIFT / io_uring Page Cache)..." << std::endl;
    }

    // --- CRITICAL FIX 1: Allocate RAM for 10,000 centroids ---
    std::vector<float> centroids(10000 * 128); 
    std::ifstream cent_file("centroids.bin", std::ios::binary);
    cent_file.read(reinterpret_cast<char*>(centroids.data()), centroids.size() * sizeof(float));
    cent_file.close();

    std::vector<float> global_mean(128);
    std::ifstream gm_file("global_mean.bin", std::ios::binary);
    gm_file.read(reinterpret_cast<char*>(global_mean.data()), 128 * sizeof(float));
    gm_file.close();

    std::ifstream json_file("segment_table.json");
    json j = json::parse(json_file);
    std::unordered_map<int, ClusterInfo> segment_table;
    
    size_t max_cluster_bytes = 0;
    for (auto& [key, val] : j.items()) {
        size_t len_bytes = val["length_bytes"].get<size_t>();
        if (len_bytes > max_cluster_bytes) max_cluster_bytes = len_bytes;
        
        segment_table[std::stoi(key)] = {
            val["num_vectors"].get<size_t>(),
            val["byte_offset"].get<size_t>(),
            len_bytes,
            val["scale"].get<float>(),
            val["zero_point"].get<float>() 
        };
    }

    int num_queries = 10000;
    std::vector<float> test_queries(num_queries * 128);
    std::ifstream query_file("test_queries.bin", std::ios::binary);
    query_file.read(reinterpret_cast<char*>(test_queries.data()), test_queries.size() * sizeof(float));
    query_file.close();

    std::vector<uint32_t> ground_truth(num_queries * 10);
    std::ifstream gt_file("ground_truth.bin", std::ios::binary);
    gt_file.read(reinterpret_cast<char*>(ground_truth.data()), ground_truth.size() * sizeof(uint32_t));
    gt_file.close();

    int open_flags = O_RDONLY;
    if (use_direct) open_flags |= O_DIRECT;

    int tape_fd = open("index_tape.bin", open_flags);
    if (tape_fd < 0) {
        std::cerr << "[!] Failed to open index_tape.bin." << std::endl;
        return 1;
    }

    // --- CRITICAL FIX 2: Increase probes to maintain recall at 10M scale ---
    int probes = 60; // 1% of the 10,000 total clusters 

    void* aligned_master_buffer = nullptr;
    if (posix_memalign(&aligned_master_buffer, 4096, max_cluster_bytes * probes) != 0) return 1;
    char* buffer_pool = static_cast<char*>(aligned_master_buffer);

    // --- CRITICAL FIX 3: Expand the io_uring queue depth to hold up to 256 parallel requests ---
    struct io_uring ring;
    if (io_uring_queue_init(256, &ring, 0) < 0) { 
        std::cerr << "[!] Failed to initialize io_uring." << std::endl;
        return 1;
    }

    if (!use_direct) {
        std::cout << "[*] Performing warm-up pass (1000 queries) to populate Linux Page Cache..." << std::endl;
        for (int q = 0; q < 1000; ++q) {
            const float* current_query = &test_queries[q * 128];
            std::priority_queue<std::pair<float, int>> cluster_pq;
            for (int i = 0; i < 10000; ++i) { 
                float dist = l2_distance_float_simd(current_query, &centroids[i * 128]);
                if (cluster_pq.size() < probes) cluster_pq.push({dist, i});
                else if (dist < cluster_pq.top().first) { cluster_pq.pop(); cluster_pq.push({dist, i}); }
            }
            std::vector<int> target_clusters(probes);
            for (int i = probes - 1; i >= 0; --i) { target_clusters[i] = cluster_pq.top().second; cluster_pq.pop(); }
            
            for (int i = 0; i < probes; ++i) {
                int cluster_id = target_clusters[i];
                ClusterInfo info = segment_table[cluster_id];
                struct io_uring_sqe *sqe = io_uring_get_sqe(&ring);
                io_uring_prep_read(sqe, tape_fd, buffer_pool + (i * max_cluster_bytes), 
                                   info.length_bytes, info.byte_offset);
            }
            io_uring_submit(&ring);
            for (int i = 0; i < probes; ++i) {
                struct io_uring_cqe *cqe;
                io_uring_wait_cqe(&ring, &cqe);
                io_uring_cqe_seen(&ring, cqe);
            }
        }
        std::cout << "[+] Warm-up complete. Starting timed benchmark." << std::endl;
    }

    std::cout << "[+] io_uring initialized. Async SSD Pool Size: " << (max_cluster_bytes * probes / 1024 / 1024) << " MB." << std::endl;
    std::cout << "[+] Running 10,000 queries...\n" << std::endl;

    int bitmask_threshold = 45; 
    
    double total_recall = 0.0;
    double total_latency_ms = 0.0;
    long long total_simd_avoided = 0;

    for (int q = 0; q < num_queries; ++q) {
        const float* current_query = &test_queries[q * 128];
        auto start_time = std::chrono::high_resolution_clock::now();

        uint64_t q_mask[2] = {0, 0};
        for(int j=0; j<64; ++j) {
            if (current_query[j] > global_mean[j]) q_mask[0] |= (1ULL << j);
            if (current_query[j+64] > global_mean[j+64]) q_mask[1] |= (1ULL << j);
        }

        std::priority_queue<std::pair<float, int>> cluster_pq;
        
        for (int i = 0; i < 10000; ++i) { 
            float dist = l2_distance_float_simd(current_query, &centroids[i * 128]);
            if (cluster_pq.size() < probes) {
                cluster_pq.push({dist, i});
            } else if (dist < cluster_pq.top().first) {
                cluster_pq.pop();
                cluster_pq.push({dist, i});
            }
        }

        std::vector<int> target_clusters(probes);
        for (int i = probes - 1; i >= 0; --i) {
            target_clusters[i] = cluster_pq.top().second;
            cluster_pq.pop();
        }

        std::priority_queue<std::pair<float, uint32_t>> top_k_results;
        ClusterInfo active_infos[probes];

        for (int i = 0; i < probes; ++i) {
            int cluster_id = target_clusters[i];
            active_infos[i] = segment_table[cluster_id];
            
            struct io_uring_sqe *sqe = io_uring_get_sqe(&ring);
            io_uring_prep_read(sqe, tape_fd, buffer_pool + (i * max_cluster_bytes), 
                                active_infos[i].length_bytes, active_infos[i].byte_offset);
            io_uring_sqe_set_data(sqe, (void*)(uintptr_t)i);
        }
        
        io_uring_submit(&ring);

        for (int i = 0; i < probes; ++i) {
            struct io_uring_cqe *cqe;
            io_uring_wait_cqe(&ring, &cqe);
            
            int slot = (int)(uintptr_t)io_uring_cqe_get_data(cqe);
            ClusterInfo info = active_infos[slot];
            
            VectorRecord* records = reinterpret_cast<VectorRecord*>(buffer_pool + (slot * max_cluster_bytes));

            for (size_t v = 0; v < info.num_vectors; ++v) {
                int hamming_dist = __builtin_popcountll(q_mask[0] ^ records[v].bitmask[0]) + 
                                   __builtin_popcountll(q_mask[1] ^ records[v].bitmask[1]);

                if (hamming_dist > bitmask_threshold) {
                    total_simd_avoided++;
                    continue; 
                }

                float dist = l2_distance_simd_int8_asymmetric(current_query, records[v].vector, info.scale, info.zero_point);
                
                if (top_k_results.size() < 10) {
                    top_k_results.push({dist, records[v].id});
                } else if (dist < top_k_results.top().first) {
                    top_k_results.pop();
                    top_k_results.push({dist, records[v].id});
                }
            }
            io_uring_cqe_seen(&ring, cqe);
        }

        auto end_time = std::chrono::high_resolution_clock::now();
        std::chrono::duration<double, std::milli> latency = end_time - start_time;
        total_latency_ms += latency.count();

        std::unordered_set<uint32_t> true_nn;
        for (int j = 0; j < 10; ++j) true_nn.insert(ground_truth[q * 10 + j]);

        int matches = 0;
        while (!top_k_results.empty()) {
            if (true_nn.find(top_k_results.top().second) != true_nn.end()) matches++;
            top_k_results.pop();
        }
        total_recall += (matches / 10.0);

        if ((q + 1) % 1000 == 0) std::cout << "Processed " << (q + 1) << " / 10000 queries..." << std::endl;
    }

    std::cout << "\n=========================================" << std::endl;
    if (use_direct) {
        std::cout << "        10M SCALE O_DIRECT BARE METAL      " << std::endl;
    } else {
        std::cout << "        10M SCALE LINUX PAGE CACHE        " << std::endl;
    }
    std::cout << "=========================================" << std::endl;
    std::cout << "Probes per query : " << probes << " clusters" << std::endl;
    std::cout << "Average Latency  : " << (total_latency_ms / num_queries) << " ms" << std::endl;
    std::cout << "Recall@10        : " << (total_recall / num_queries) * 100.0 << " %" << std::endl;
    std::cout << "SIMD Calcs Saved : " << total_simd_avoided << " vectors skipped!" << std::endl;
    std::cout << "=========================================" << std::endl;

    io_uring_queue_exit(&ring);
    free(aligned_master_buffer);
    close(tape_fd);
    return 0;
}

*/