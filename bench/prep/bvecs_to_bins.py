"""
Convert BIGANN bvecs files to float32 .bin files for TAPEANN and DiskANN.

Replaces TAPEANN's split_dataset.py + export_test.py (which assume HDF5 .mat input).

Output:
  data/tape/sift10m_base_disjoint.bin  -- raw float32, no header  (TAPEANN)
  data/tape/test_queries.bin           -- raw float32, no header  (TAPEANN)
  data/diskann/base.fbin               -- [u32 n][u32 d][float32] (DiskANN)
  data/diskann/query.fbin              -- [u32 n][u32 d][float32] (DiskANN)

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


def write_diskann_bin(arr, path):
    """Write (n, d) float32 with [uint32 n][uint32 d] header."""
    n, d = arr.shape
    with open(path, "wb") as f:
        np.array([n, d], dtype=np.uint32).tofile(f)
        arr.astype(np.float32).tofile(f)


def main():
    for d in (TAPE_DIR, DISKANN_DIR):
        os.makedirs(d, exist_ok=True)

    # ---- Queries (10k × 128, tiny — load all at once) ----
    print(f"[1/2] Queries: {QUERY_BVECS}")
    queries, dim = bvecs_to_array(QUERY_BVECS)
    print(f"      {queries.shape[0]:,} vectors × dim={dim}")

    query_tape    = os.path.join(TAPE_DIR,    "test_queries.bin")
    query_diskann = os.path.join(DISKANN_DIR, "query.fbin")
    queries.astype(np.float32).tofile(query_tape)
    write_diskann_bin(queries, query_diskann)
    print(f"      → {query_tape}")
    print(f"      → {query_diskann}")

    # ---- Base vectors (10M × 128, chunked) ----
    record_size      = 4 + dim
    file_bytes       = os.path.getsize(BASE_BVECS)
    total_vecs       = file_bytes // record_size

    print(f"\n[2/2] Base vectors: {BASE_BVECS}")
    print(f"      {total_vecs:,} vectors × dim={dim}  "
          f"→ {total_vecs * dim * 4 / 1e9:.2f} GB float32 output each")

    base_tape    = os.path.join(TAPE_DIR,    "sift10m_base_disjoint.bin")
    base_diskann = os.path.join(DISKANN_DIR, "base.fbin")

    written = 0
    with open(base_tape, "wb") as ft, open(base_diskann, "wb") as fd:
        # DiskANN header placeholder — patched after the loop
        fd.write(np.zeros(2, dtype=np.uint32).tobytes())

        with tqdm(total=total_vecs, unit="vec", unit_scale=True,
                  unit_divisor=1000, desc="  converting",
                  bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} vecs "
                             "[{elapsed}<{remaining}, {rate_fmt}]") as pbar:
            for chunk, _ in read_bvecs_chunked(BASE_BVECS):
                chunk.astype(np.float32).tofile(ft)
                chunk.astype(np.float32).tofile(fd)
                written += len(chunk)
                pbar.update(len(chunk))

        fd.seek(0)
        np.array([written, dim], dtype=np.uint32).tofile(fd)

    tape_bytes = os.path.getsize(base_tape)
    assert tape_bytes == written * dim * 4, \
        f"Size mismatch: {tape_bytes} vs {written * dim * 4}"

    print(f"\n      → {base_tape}  ({tape_bytes/1e9:.2f} GB)")
    print(f"      → {base_diskann}  ({os.path.getsize(base_diskann)/1e9:.2f} GB)")
    print(f"\n[+] Done. {written:,} base vectors converted.")


if __name__ == "__main__":
    main()
