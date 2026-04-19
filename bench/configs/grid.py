"""
Parameter grids and paths for the TAPEANN vs DiskANN benchmark.
"""

import os

REPO_ROOT   = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ---- Data paths ----
DATA        = os.path.join(REPO_ROOT, "data")
TAPE_DATA   = os.path.join(DATA, "tape")
DISKANN_DATA= os.path.join(DATA, "diskann")
GT_DIR      = os.path.join(DATA, "gt")
IDX_DIR     = os.path.join(DATA, "idx")

# ---- Binary / script paths ----
TAPE_WRITER     = os.path.join(REPO_ROOT, "sift10m_code", "ram_algo_implementation", "tape_writer.py")
TAPE_BENCH_SRC  = os.path.join(REPO_ROOT, "sift10m_code", "ram_algo_implementation", "benchmark_search.cpp")
TAPE_BENCH_BIN  = os.path.join(TAPE_DATA, "benchmark_search")   # compiled binary lives in data/tape/

DISKANN_BENCH   = os.path.join(REPO_ROOT, "DiskANN", "target", "release", "diskann-benchmark")

DISKANN_INDEX_PREFIX = os.path.join(IDX_DIR, "diskann_sift10m")
DISKANN_BASE    = os.path.join(DISKANN_DATA, "base.fbin")
DISKANN_QUERY   = os.path.join(DISKANN_DATA, "query.fbin")
DISKANN_GT      = os.path.join(GT_DIR, "gt100.diskann.bin")

# ---- Results / logs ----
RESULTS_DIR = os.path.join(REPO_ROOT, "bench", "results")
LOGS_DIR    = os.path.join(REPO_ROOT, "bench", "logs")
PLOTS_DIR   = os.path.join(REPO_ROOT, "bench", "plots")

# ---- TAPEANN search grid ----
# probes: number of clusters to read per query (max io_uring queue = 256)
TAPE_PROBES = [10, 25, 50, 100, 150, 200, 256]

# cache_mode: "direct"    = O_DIRECT, cold on every query (strictest cold)
#             "drop_once" = page-cache, drop-caches once then measure (matches DiskANN "cold")
#             "cache"     = page-cache + 1000-query warmup (steady-state warm)
TAPE_CACHE_MODES = ["direct", "drop_once", "cache"]

# ---- Trial repetition ----
# Each (algo, mode, param...) config is run TRIALS times; aggregation is done in analyze.py.
TRIALS = 3

# ---- DiskANN search grid ----
DISKANN_L_SEARCH  = [10, 20, 30, 50, 75, 100, 150]
DISKANN_BEAMWIDTH = [1, 2, 4, 8]
DISKANN_CACHE_MODES = ["cold", "warm"]

# Warm mode: cache this many nodes from the graph into DRAM
DISKANN_WARM_CACHE_NODES = 200_000

# ---- Search common ----
NUM_QUERIES = 10_000
K           = 10   # recall@K
