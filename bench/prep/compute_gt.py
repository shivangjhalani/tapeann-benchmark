"""
Compute ground truth for SIFT10M (top-100 exact NN) via FAISS brute force.

Both TAPEANN and DiskANN score against this identical ground truth.

Output:
  data/tape/ground_truth.bin     -- uint32 (10000 × 10)    TAPEANN (k=10 slice)
  data/gt/gt100.diskann.bin      -- DiskANN binary GT format (k=100)

DiskANN GT format:
  [uint32 n_queries][uint32 k][uint32 ids n×k row-major][float32 dists n×k row-major]

Run from repo root:  python bench/prep/compute_gt.py
Memory requirement:  ~6 GB RAM (IndexFlatL2 on 10M × 128 float32)
"""

import os
import time
import numpy as np
import faiss
from tqdm import tqdm

REPO_ROOT   = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TAPE_DIR    = os.path.join(REPO_ROOT, "data", "tape")
GT_DIR      = os.path.join(REPO_ROOT, "data", "gt")

BASE_BIN    = os.path.join(TAPE_DIR, "sift10m_base_disjoint.bin")
QUERY_BIN   = os.path.join(TAPE_DIR, "test_queries.bin")
GT_TAPE     = os.path.join(TAPE_DIR, "ground_truth.bin")
GT_DISKANN  = os.path.join(GT_DIR,   "gt100.diskann.bin")

K_GT   = 100
K_TAPE = 10
DIM    = 128
ADD_CHUNK = 500_000


def load_raw_bin(path, dim):
    data = np.fromfile(path, dtype=np.float32)
    return data.reshape(-1, dim)


def write_diskann_gt(ids, dists, path):
    n, k = ids.shape
    with open(path, "wb") as f:
        np.array([n, k], dtype=np.uint32).tofile(f)
        ids.astype(np.uint32).tofile(f)
        dists.astype(np.float32).tofile(f)


def main():
    os.makedirs(GT_DIR, exist_ok=True)

    # ---- Load vectors ----
    print(f"[1/4] Loading base vectors from {BASE_BIN} ...")
    t0 = time.time()
    base = load_raw_bin(BASE_BIN, DIM)
    print(f"      {base.shape[0]:,} × {DIM}  ({time.time()-t0:.1f}s, "
          f"{base.nbytes/1e9:.2f} GB in RAM)")

    print(f"\n[2/4] Loading query vectors from {QUERY_BIN} ...")
    queries = load_raw_bin(QUERY_BIN, DIM)
    print(f"      {queries.shape[0]:,} × {DIM}")

    # ---- Build index (chunked add with progress) ----
    print(f"\n[3/4] Building FAISS IndexFlatL2 — adding {len(base):,} vectors ...")
    index = faiss.IndexFlatL2(DIM)
    t0 = time.time()

    with tqdm(total=len(base), unit="vec", unit_scale=True, unit_divisor=1000,
              desc="  adding",
              bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} vecs "
                         "[{elapsed}<{remaining}, {rate_fmt}]") as pbar:
        for start in range(0, len(base), ADD_CHUNK):
            chunk = np.ascontiguousarray(base[start:start + ADD_CHUNK])
            index.add(chunk)
            pbar.update(len(chunk))

    print(f"      Index built in {time.time()-t0:.1f}s  ({index.ntotal:,} vectors indexed)")

    # ---- Search ----
    print(f"\n[4/4] Searching k={K_GT} for {len(queries):,} queries ...")
    t0 = time.time()
    dists, ids = index.search(np.ascontiguousarray(queries), K_GT)
    print(f"      Done in {time.time()-t0:.1f}s")

    # ---- Write outputs ----
    ids_tape = ids[:, :K_TAPE].astype(np.uint32)
    ids_tape.tofile(GT_TAPE)
    print(f"\n[+] Wrote {GT_TAPE}  ({os.path.getsize(GT_TAPE):,} bytes, k={K_TAPE})")

    write_diskann_gt(ids, dists, GT_DISKANN)
    print(f"[+] Wrote {GT_DISKANN}  ({os.path.getsize(GT_DISKANN):,} bytes, k={K_GT})")

    # ---- Sanity check ----
    print("\n[*] Sanity check: self-search on first 100 base vectors ...")
    top1 = index.search(np.ascontiguousarray(base[:100]), 1)[1].flatten()
    assert np.all(top1 == np.arange(100)), "Self-search sanity check failed!"
    print("[+] Passed — every vector's nearest neighbour is itself.")


if __name__ == "__main__":
    main()
