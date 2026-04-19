"""
Convert BIGANN bvecs files to float32 .bin files for TAPEANN and DiskANN.

Replaces TAPEANN's split_dataset.py + export_test.py (which assume HDF5 .mat input).

Output:
  data/tape/sift10m_base_disjoint.bin  -- raw float32, no header  (TAPEANN)
  data/tape/test_queries.bin           -- raw float32, no header  (TAPEANN)
  data/diskann/base.fbin               -- [u32 n][u32 d][float32] (DiskANN fp32 variant)
  data/diskann/query.fbin              -- [u32 n][u32 d][float32] (DiskANN fp32 variant)
  data/diskann/base.u8bin              -- [u32 n][u32 d][uint8]   (DiskANN uint8 variant)
  data/diskann/query.u8bin             -- [u32 n][u32 d][uint8]   (DiskANN uint8 variant)

Idempotent: any output whose size matches n*d*sizeof(dtype)+8 is skipped.
Run from repo root:  python bench/prep/bvecs_to_bins.py
"""

import os
import sys
import numpy as np
from tqdm import tqdm

REPO_ROOT   = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RAW_DIR     = os.path.join(REPO_ROOT, "data", "raw")
TAPE_DIR    = os.path.join(REPO_ROOT, "data", "tape")
DISKANN_DIR = os.path.join(REPO_ROOT, "data", "diskann")

BASE_BVECS  = os.path.join(RAW_DIR, "bigann_base_10M.bvecs")
QUERY_BVECS = os.path.join(RAW_DIR, "bigann_query.bvecs")

CHUNK_ROWS = 500_000


def _peek_dim(path):
    with open(path, "rb") as f:
        return int(np.frombuffer(f.read(4), dtype=np.int32)[0])


def read_bvecs_chunked(path, chunk_rows=CHUNK_ROWS):
    """Yield (float32 array of shape (n, dim), dim) for each chunk."""
    dim = _peek_dim(path)
    record_size = 4 + dim
    with open(path, "rb") as f:
        while True:
            raw = f.read(record_size * chunk_rows)
            if not raw:
                break
            n_read = len(raw) // record_size
            data = np.frombuffer(raw[:n_read * record_size], dtype=np.uint8)
            yield data.reshape(n_read, record_size)[:, 4:].astype(np.float32), dim


def bvecs_to_array(path):
    """Read a full bvecs file into a (n, dim) float32 array."""
    chunks, dim = [], None
    for chunk, d in read_bvecs_chunked(path):
        chunks.append(chunk)
        dim = d
    return np.vstack(chunks), dim


def write_diskann_bin(arr, path, dtype=np.float32):
    """Write (n, d) matrix as DiskANN .bin: [u32 n][u32 d][dtype payload]."""
    n, d = arr.shape
    with open(path, "wb") as f:
        np.array([n, d], dtype=np.uint32).tofile(f)
        arr.astype(dtype).tofile(f)


def _expected_bin_size(n, d, itemsize):
    return 8 + n * d * itemsize


def _is_complete(path, n, d, itemsize):
    return os.path.exists(path) and os.path.getsize(path) == _expected_bin_size(n, d, itemsize)


def main():
    for d in (TAPE_DIR, DISKANN_DIR):
        os.makedirs(d, exist_ok=True)

    # ---- Queries (10k × 128, tiny — load all at once) ----
    print(f"[1/2] Queries: {QUERY_BVECS}")
    queries, dim = bvecs_to_array(QUERY_BVECS)
    print(f"      {queries.shape[0]:,} vectors × dim={dim}")

    query_tape    = os.path.join(TAPE_DIR,    "test_queries.bin")
    query_fbin    = os.path.join(DISKANN_DIR, "query.fbin")
    query_u8bin   = os.path.join(DISKANN_DIR, "query.u8bin")
    nq = queries.shape[0]

    if os.path.getsize(query_tape) != nq * dim * 4 if os.path.exists(query_tape) else True:
        queries.astype(np.float32).tofile(query_tape)
    print(f"      → {query_tape}")

    if not _is_complete(query_fbin, nq, dim, 4):
        write_diskann_bin(queries, query_fbin, dtype=np.float32)
    print(f"      → {query_fbin}")

    if not _is_complete(query_u8bin, nq, dim, 1):
        # Queries are uint8 in source; clamp to safe range before cast.
        q_u8 = np.clip(queries, 0, 255).astype(np.uint8)
        write_diskann_bin(q_u8, query_u8bin, dtype=np.uint8)
    print(f"      → {query_u8bin}")

    # ---- Base vectors (10M × 128, chunked) ----
    record_size      = 4 + dim
    file_bytes       = os.path.getsize(BASE_BVECS)
    total_vecs       = file_bytes // record_size

    print(f"\n[2/2] Base vectors: {BASE_BVECS}")
    print(f"      {total_vecs:,} vectors × dim={dim}  "
          f"→ {total_vecs * dim * 4 / 1e9:.2f} GB float32 output each")

    base_tape   = os.path.join(TAPE_DIR,    "sift10m_base_disjoint.bin")
    base_fbin   = os.path.join(DISKANN_DIR, "base.fbin")
    base_u8bin  = os.path.join(DISKANN_DIR, "base.u8bin")

    do_tape  = not (os.path.exists(base_tape)  and os.path.getsize(base_tape)  == total_vecs * dim * 4)
    do_fbin  = not _is_complete(base_fbin,  total_vecs, dim, 4)
    do_u8bin = not _is_complete(base_u8bin, total_vecs, dim, 1)

    if not (do_tape or do_fbin or do_u8bin):
        print("      All base outputs already complete — skipping.")
        return

    written = 0
    ft  = open(base_tape,  "wb") if do_tape  else None
    ff  = open(base_fbin,  "wb") if do_fbin  else None
    fu  = open(base_u8bin, "wb") if do_u8bin else None
    try:
        if ff: ff.write(np.zeros(2, dtype=np.uint32).tobytes())   # header placeholder
        if fu: fu.write(np.zeros(2, dtype=np.uint32).tobytes())

        with tqdm(total=total_vecs, unit="vec", unit_scale=True,
                  unit_divisor=1000, desc="  converting",
                  bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} vecs "
                             "[{elapsed}<{remaining}, {rate_fmt}]") as pbar:
            for chunk, _ in read_bvecs_chunked(BASE_BVECS):
                if ft: chunk.astype(np.float32).tofile(ft)
                if ff: chunk.astype(np.float32).tofile(ff)
                if fu: np.clip(chunk, 0, 255).astype(np.uint8).tofile(fu)
                written += len(chunk)
                pbar.update(len(chunk))

        if ff:
            ff.seek(0); np.array([written, dim], dtype=np.uint32).tofile(ff)
        if fu:
            fu.seek(0); np.array([written, dim], dtype=np.uint32).tofile(fu)
    finally:
        for f in (ft, ff, fu):
            if f: f.close()

    for label, path in [("tape fp32", base_tape), ("diskann fp32", base_fbin),
                        ("diskann u8",  base_u8bin)]:
        if os.path.exists(path):
            print(f"      → {label:<14} {path}  ({os.path.getsize(path)/1e9:.2f} GB)")
    print(f"\n[+] Done. {written:,} base vectors converted.")


if __name__ == "__main__":
    main()
