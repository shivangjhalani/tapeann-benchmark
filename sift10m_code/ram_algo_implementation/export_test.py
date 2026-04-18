import numpy as np
import time
import faiss

print("[*] Loading Disjoint Base and Queries directly from RAM...")
start_time = time.time()

# Load the raw float32 binaries directly
base_f32 = np.fromfile("sift10m_base_disjoint.bin", dtype=np.float32).reshape(-1, 128)
queries_f32 = np.fromfile("test_queries_disjoint.bin", dtype=np.float32).reshape(-1, 128)

print(f"[+] Loaded in {time.time() - start_time:.2f}s")
print(f"    Base: {base_f32.shape}")
print(f"    Queries: {queries_f32.shape}")

# We only need Top-10 for the recall metric
TOP_K = 10

print(f"\n[*] Computing EXACT Disjoint Top-{TOP_K} Ground Truth using FAISS (AVX2)...")
gt_start = time.time()

# Build the exact L2 index and search all 16 threads
index = faiss.IndexFlatL2(128)
index.add(base_f32)
distances, indices = index.search(queries_f32, TOP_K)

print(f"[+] Ground truth calculated in {time.time() - gt_start:.2f}s")

# Save as uint32 to perfectly match the C++ VectorRecord struct
ground_truth = indices.astype(np.uint32)
ground_truth.tofile("ground_truth.bin")

# Overwrite the old test_queries.bin so the C++ engine uses the disjoint ones
queries_f32.tofile("test_queries.bin")

print("[+] Saved ground_truth.bin and test_queries.bin")
print("[+] YOU ARE OFFICIALLY READY FOR THE FINAL C++ BENCHMARK.")