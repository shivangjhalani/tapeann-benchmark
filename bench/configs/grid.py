"""
Central config: datasets, index variants, cache modes, param grids, paths.

Everything downstream (build scripts, runners, analyzers) reads from here.
No YAML — plain Python dicts keep imports simple and let us compute derived
values (paths, budget calculations) in one place.
"""

import os

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ─── Top-level paths ─────────────────────────────────────────────────────────
DATA_ROOT    = os.path.join(REPO_ROOT, "data")
RAW_DIR      = os.path.join(DATA_ROOT, "raw")
TAPE_DATA    = os.path.join(DATA_ROOT, "tape")
DISKANN_DATA = os.path.join(DATA_ROOT, "diskann")
GT_DIR       = os.path.join(DATA_ROOT, "gt")
IDX_DIR      = os.path.join(DATA_ROOT, "idx")

RESULTS_DIR = os.path.join(REPO_ROOT, "bench", "results")
LOGS_DIR    = os.path.join(REPO_ROOT, "bench", "logs")
PLOTS_DIR   = os.path.join(RESULTS_DIR, "plots")

# Result CSVs (new unified schema, replaces old per-algo CSVs)
RUNS_CSV        = os.path.join(RESULTS_DIR, "runs.csv")
BUILD_COSTS_CSV = os.path.join(RESULTS_DIR, "build_costs.csv")
INDEX_SIZES_TXT = os.path.join(RESULTS_DIR, "index_sizes.txt")
ENV_TXT         = os.path.join(RESULTS_DIR, "env.txt")

# ─── Binaries / source paths ─────────────────────────────────────────────────
TAPE_SRC_DIR    = os.path.join(REPO_ROOT, "sift10m_code", "ram_algo_implementation")
TAPE_WRITER     = os.path.join(TAPE_SRC_DIR, "tape_writer.py")
TAPE_BENCH_SRC  = os.path.join(TAPE_SRC_DIR, "benchmark_search.cpp")
TAPE_BENCH_BIN  = os.path.join(TAPE_DATA, "benchmark_search")

DISKANN_BENCH   = os.path.join(REPO_ROOT, "DiskANN", "target", "release",
                               "diskann-benchmark")

# ─── Datasets ────────────────────────────────────────────────────────────────
#   nvecs        : number of base vectors
#   dim          : vector dimension
#   raw_bvecs    : input file (bigann_base_{profile}.bvecs, uint8 bvecs format)
#   query_bvecs  : query file (bigann_query.bvecs)
#   n_queries    : number of queries to measure on
#
# Only sift10m is active; sift1m and sift100m are declared so builders
# and runners can accept them later without code changes.

DATASETS = {
    "sift1m": {
        "nvecs":       1_000_000,
        "dim":         128,
        "raw_bvecs":   os.path.join(RAW_DIR, "bigann_base_sift1m.bvecs"),
        "query_bvecs": os.path.join(RAW_DIR, "bigann_query.bvecs"),
        "n_queries":   10_000,
    },
    "sift10m": {
        "nvecs":       10_000_000,
        "dim":         128,
        "raw_bvecs":   os.path.join(RAW_DIR, "bigann_base_10M.bvecs"),  # legacy name
        "query_bvecs": os.path.join(RAW_DIR, "bigann_query.bvecs"),
        "n_queries":   10_000,
    },
    "sift100m": {
        "nvecs":       100_000_000,
        "dim":         128,
        "raw_bvecs":   os.path.join(RAW_DIR, "bigann_base_sift100m.bvecs"),
        "query_bvecs": os.path.join(RAW_DIR, "bigann_query.bvecs"),
        "n_queries":   10_000,
    },
}

ACTIVE_DATASETS = ["sift10m"]  # sweep targets

# ─── Index build variants ────────────────────────────────────────────────────
# Keyed by variant name; consumed by build scripts.

TAPE_VARIANTS = {
    "tape_int8": {
        "algo":        "tapeann",
        "quant":       "int8",        # asymmetric int8 (existing)
        "n_clusters":  10_000,
        "dim_pca":     8,
    },
    "tape_fp32": {
        "algo":        "tapeann",
        "quant":       "fp32",        # requires benchmark_search.cpp update to load fp32 tape
        "n_clusters":  10_000,
        "dim_pca":     8,
    },
}

DISKANN_VARIANTS = {
    # Existing fp32 build (kept as-is). PQ chunks ~64 MB for 10M × 128d.
    "diskann_fp32_pq64": {
        "algo":          "diskann",
        "data_type":     "float32",
        "base_suffix":   "fbin",
        "R":             64,
        "L_build":       100,
        "num_pq_chunks": 64,
        "M_ram_GB":      32,
    },
    # Matched-byte build: BIGANN is natively uint8; this is the fair head-to-head
    # against TAPE int8 (same bytes/vector, same bits of precision in the vector
    # store).
    "diskann_uint8_pq32": {
        "algo":          "diskann",
        "data_type":     "uint8",
        "base_suffix":   "u8bin",
        "R":             64,
        "L_build":       100,
        "num_pq_chunks": 32,
        "M_ram_GB":      32,
    },
    "diskann_uint8_pq64": {
        "algo":          "diskann",
        "data_type":     "uint8",
        "base_suffix":   "u8bin",
        "R":             64,
        "L_build":       100,
        "num_pq_chunks": 64,
        "M_ram_GB":      32,
    },
}

# tape_fp32 is declared in TAPE_VARIANTS but not active: the current
# benchmark_search.cpp and tape_writer only support int8 layout. Adding
# fp32 would require a new record format + writer; deferred per disk budget.
ACTIVE_VARIANTS = [
    "tape_int8",
    "diskann_fp32_pq64",
    "diskann_uint8_pq32",
    "diskann_uint8_pq64",
]

# ─── Cache / memory regimes ──────────────────────────────────────────────────
# Applied uniformly to both systems.
#
#   cold_strict : truly cold per-query
#                 - tape:    O_DIRECT flag
#                 - diskann: drop_caches before each query batch (approximation;
#                            the Rust binary is one process, so per-query is
#                            impractical — we use per-run + posix_fadvise
#                            DONTNEED wrapper).
#   cold_start  : drop_caches once; page cache warms naturally during the run
#   warm_steady : 2000-query warmup discarded, then measure
#   ram_capped_* : run under systemd-run scope with MemoryMax = fraction of
#                  the on-disk index bytes (forces real disk I/O even when
#                  physical RAM is huge)

# ram_cap is absolute bytes (or None). Two modes only:
#   warm            — everything in RAM; measures CPU/algorithm efficiency.
#   ram_capped_4gb  — cgroup-capped at 4 GB with drop_caches; forces real disk I/O
#                     for BOTH systems at the SAME literal budget (fair apples-to-apples).
# The old cold_strict/cold_start/ram_capped_{25,50} modes are kept defined for
# reference but are not in ACTIVE_MODES — their semantics weren't symmetric.

_GB = 1024 ** 3
MODES = {
    "warm":              {"drop_caches": False, "warmup_queries": 1000, "ram_cap": None,             "o_direct": False},
    # 1.5 GB cap forces BOTH indices to page: tape_int8 is ~1.67 GB, DiskANN
    # uint8_pq64 is ~6.8 GB — so neither fits entirely in the cap.
    "ram_capped_1p5gb":  {"drop_caches": True,  "warmup_queries": 0,    "ram_cap": (3 * _GB) // 2,   "o_direct": False},
}

ACTIVE_MODES = ["warm", "ram_capped_1p5gb"]

# ─── Query parameter grids ───────────────────────────────────────────────────
# TAPE: probes sweep. The C++ binary now sizes the io_uring ring dynamically
# from `probes`, so the old 256 cap is gone. 1000 probes ≈ 10% of clusters;
# that's enough to push recall past 99%.

TAPE_PROBES = [10, 15, 20, 25, 30, 35, 40, 50, 70, 100, 150, 200, 300, 500, 750, 1000]

# DiskANN: L × beamwidth. Added L=300 for ≥99% recall headroom.
DISKANN_L_SEARCH  = [10, 20, 30, 50, 75, 100, 150, 200, 300]
DISKANN_BEAMWIDTH = [1, 2, 4]

# ─── Thread grid ─────────────────────────────────────────────────────────────
# Default sweep runs single-threaded only; the run_all.py --thread-sweep flag
# enables the wider thread grid at a canonical operating point per variant.
THREADS_DEFAULT = [1]
THREADS_SWEEP   = [1, 2, 4, 8, 16]

# Canonical (~95% recall) operating points used by --thread-sweep. Keeps the
# thread-scaling experiment to a tractable size instead of re-running the full
# param grid at every thread count.
# tape_int8 is intentionally absent: benchmark_search.cpp is single-threaded
# (one io_uring + one scorer), so threads > 1 would reproduce the same number.
# The thread sweep measures DiskANN's scaling at a fixed ~95% recall point.
THREAD_SWEEP_PARAMS = {
    "diskann_uint8_pq64":  [{"L": 30, "W": 4}],
    "diskann_fp32_pq64":   [{"L": 30, "W": 4}],
    "diskann_uint8_pq32":  [{"L": 30, "W": 4}],
}

# ─── Trials / rep ────────────────────────────────────────────────────────────
TRIALS = 3
K      = 10          # recall@K
K_GT   = 100         # ground truth depth

# ─── Unified runs.csv schema ─────────────────────────────────────────────────
RUNS_COLS = [
    "algo", "dataset", "variant", "mode", "ram_cap_bytes",
    "params_json",           # {"L":..,"W":..} or {"probes":..,"rerank":..}
    "threads", "trial",
    "recall1", "recall10", "recall100",
    "qps", "mean_ms", "p50_ms", "p95_ms", "p99_ms", "p999_ms",
    # bytes_read_* come from /proc/{pid}/io (bytes that actually hit the block
    # layer — legitimately 0 when the page cache served the request).
    # bytes_per_query_app is the application-requested byte budget (sum of
    # read lengths the algorithm asked for). The "fair" bytes/query metric
    # for cross-system comparison.
    "bytes_read_total", "bytes_read_per_query", "bytes_per_query_app",
    "ios_total", "ios_per_query",
    "simd_distance_calls", "simd_avoided",
    "cpu_user_s", "cpu_sys_s", "peak_rss_mb", "wall_s",
    "commit_sha",
]

BUILD_COSTS_COLS = [
    "algo", "variant", "dataset",
    "build_wall_s", "build_peak_rss_mb", "build_cpu_user_s", "build_cpu_sys_s",
    "index_total_bytes", "index_files_json",
    "commit_sha", "timestamp",
]


# ─── Helpers ─────────────────────────────────────────────────────────────────
def variant_index_dir(variant: str, dataset: str) -> str:
    """Per-(variant,dataset) index directory under data/idx/."""
    return os.path.join(IDX_DIR, f"{variant}__{dataset}")


def ensure_dirs():
    for d in (DATA_ROOT, RAW_DIR, TAPE_DATA, DISKANN_DATA, GT_DIR, IDX_DIR,
              RESULTS_DIR, LOGS_DIR, PLOTS_DIR):
        os.makedirs(d, exist_ok=True)
