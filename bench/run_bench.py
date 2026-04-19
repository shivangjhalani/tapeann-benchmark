"""
Benchmark runner for TAPEANN vs DiskANN on SIFT10M.

Usage:
  python bench/run_bench.py [--algo tapeann|diskann|all] [--mode cold|warm|all]

Before running:
  1. bash bench/prep/download_data.sh
  2. python bench/prep/bvecs_to_bins.py
  3. python bench/prep/compute_gt.py
  4. python bench/run_bench.py --build       (builds TAPEANN index)
  5. python bench/run_bench.py               (runs all searches)

DiskANN uses the Rust diskann-benchmark binary (DiskANN/target/release/diskann-benchmark).
Build it with:
  cd DiskANN && RUSTFLAGS="-Ctarget-cpu=x86-64-v3" cargo build --release --features disk-index -p diskann-benchmark

Results written to bench/results/{tapeann,diskann}.csv
Each run is resumable — already-complete (algo, mode, params) rows are skipped.
"""

import argparse
import csv
import os
import re
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from configs.grid import *

TAPE_CSV    = os.path.join(RESULTS_DIR, "tapeann.csv")
DISKANN_CSV = os.path.join(RESULTS_DIR, "diskann.csv")
INDEX_SIZES = os.path.join(RESULTS_DIR, "index_sizes.txt")

TAPE_COLS = ["algo", "mode", "probes", "trial", "threads",
             "recall10", "recall1", "qps",
             "mean_ms", "p50_ms", "p95_ms", "p99_ms", "p999_ms",
             "ios_per_q", "simd_avoided", "peak_rss_mb", "wall_s"]

DISKANN_COLS = ["algo", "mode", "L", "beamwidth", "trial", "threads",
                "qps", "mean_us", "p999_us", "mean_ios", "recall10",
                "peak_rss_mb", "wall_s"]


# ---- Formatting helpers ----

def _hr(char="─", width=64):
    print(char * width)

def _section(title):
    _hr("═")
    print(f"  {title}")
    _hr("═")

def _run_header(run_num, total, label, eta_str):
    _hr()
    tag = f"[{run_num}/{total}]"
    print(f"  {tag}  {label}  {eta_str}")
    _hr()

def _fmt_eta(run_times, remaining):
    if len(run_times) < 2 or remaining <= 0:
        return ""
    avg = sum(run_times) / len(run_times)
    secs = avg * remaining
    if secs < 60:
        return f"(ETA ~{secs:.0f}s)"
    if secs < 3600:
        return f"(ETA ~{secs/60:.1f} min)"
    return f"(ETA ~{secs/3600:.1f} h)"


# ---- CSV helpers ----

def _load_done(csv_path, key_cols):
    done = set()
    if not os.path.exists(csv_path):
        return done
    with open(csv_path) as f:
        for row in csv.DictReader(f):
            done.add(tuple(row[c] for c in key_cols))
    return done


def _append_row(csv_path, cols, row):
    os.makedirs(RESULTS_DIR, exist_ok=True)
    write_header = not os.path.exists(csv_path)
    with open(csv_path, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        if write_header:
            w.writeheader()
        w.writerow(row)


# ---- Cache drop ----

def drop_caches():
    try:
        subprocess.run(["sync"], check=True)
        with open("/proc/sys/vm/drop_caches", "w") as f:
            f.write("3\n")
        print("  [cache] Page cache dropped.")
    except PermissionError:
        print("  [cache] WARNING: cannot drop caches (need root).")
        print("          Run: sudo sh -c 'sync; echo 3 > /proc/sys/vm/drop_caches'")


# ---- RSS helpers ----
# /usr/bin/time -v writes "Maximum resident set size (kbytes): N" to stderr.
# We wrap every measured subprocess with it to capture peak RSS without
# adding in-binary instrumentation.

TIME_BIN = "/usr/bin/time"

def _wrap_time(cmd):
    """Prepend /usr/bin/time -v if available; else return cmd unchanged."""
    if os.path.exists(TIME_BIN):
        return [TIME_BIN, "-v"] + list(cmd)
    return list(cmd)

_RSS_RE = re.compile(r"Maximum resident set size \(kbytes\):\s*(\d+)")

def _parse_peak_rss_mb(stderr_text):
    m = _RSS_RE.search(stderr_text or "")
    if not m:
        return "n/a"
    return round(int(m.group(1)) / 1024, 1)


# ---- Subprocess streaming ----

def _run_streaming(cmd, cwd=None, prefix="  "):
    """
    Run cmd, printing each stdout line live with `prefix`.
    Returns (returncode, full_stdout_str, full_stderr_str).
    """
    proc = subprocess.Popen(
        cmd, cwd=cwd,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, bufsize=1,
    )
    captured = []
    for line in proc.stdout:
        print(f"{prefix}{line}", end="", flush=True)
        captured.append(line)
    proc.wait()
    stderr = proc.stderr.read()
    return proc.returncode, "".join(captured), stderr


# ---- Build helpers ----

def build_tapeann():
    _section("BUILD  TAPEANN")

    print("[1/2] Compiling benchmark_search.cpp ...")
    src = TAPE_BENCH_SRC
    out = TAPE_BENCH_BIN
    cmd = ["g++", src, "-o", out, "-O3", "-march=native", "-std=c++17",
           "-luring", f"-I{os.path.dirname(src)}"]
    print(f"  $ {' '.join(cmd)}")
    rc, _, _ = _run_streaming(cmd)
    if rc != 0:
        print("[!] Compilation failed."); sys.exit(1)
    print(f"[+] Binary written to {out}")

    print("\n[2/2] Running tape_writer.py (K-means + Hilbert sort + tape write)...")
    t0 = time.time()
    rc, _, _ = _run_streaming([sys.executable, TAPE_WRITER], cwd=TAPE_DATA)
    if rc != 0:
        print("[!] tape_writer.py failed."); sys.exit(1)
    print(f"[+] tape_writer done in {time.time()-t0:.1f}s")



# ---- TAPEANN runner ----

def _parse_tape_csv(text):
    # Schema v2: algo,probes,<probes>,recall10,recall1,qps,
    #            mean_ms,p50,p95,p99,p999,ios_per_q,simd_avoided
    for line in text.splitlines():
        if line.startswith("CSV:tapeann,probes,"):
            parts = line.split(",")
            if len(parts) < 13:
                return None
            return {
                "recall10":    float(parts[3]),
                "recall1":     float(parts[4]),
                "qps":         float(parts[5]),
                "mean_ms":     float(parts[6]),
                "p50_ms":      float(parts[7]),
                "p95_ms":      float(parts[8]),
                "p99_ms":      float(parts[9]),
                "p999_ms":     float(parts[10]),
                "ios_per_q":   float(parts[11]),
                "simd_avoided":int(parts[12]),
            }
    return None


# TAPE mode → (binary flag, whether to drop caches before run)
TAPE_MODE_CONFIG = {
    "direct":    (["--direct"],               True),   # O_DIRECT, cold every query
    "drop_once": (["--cache", "--no-warmup"], True),   # page-cache, cold start, warms during run
    "cache":     (["--cache"],                False),  # page-cache + warmup pass (steady-state)
}


def run_tape_single(probes, mode, trial):
    flags, do_drop = TAPE_MODE_CONFIG[mode]
    log_path = os.path.join(LOGS_DIR, f"tape_{mode}_p{probes}_t{trial}.log")
    os.makedirs(LOGS_DIR, exist_ok=True)

    if do_drop:
        drop_caches()

    cmd = _wrap_time([TAPE_BENCH_BIN, *flags, "--probes", str(probes)])
    print(f"  $ {' '.join(cmd)}\n")

    t_start = time.time()
    rc, stdout, stderr = _run_streaming(cmd, cwd=TAPE_DATA)
    wall_s = time.time() - t_start

    with open(log_path, "w") as f:
        f.write(stdout + "\n---STDERR---\n" + stderr)

    if rc != 0:
        print(f"\n  [!] TAPEANN exited {rc}. Full log: {log_path}")
        return None

    metrics = _parse_tape_csv(stdout)
    if not metrics:
        print(f"\n  [!] Could not parse CSV line. Full log: {log_path}")
        return None

    return {
        "algo": "tapeann", "mode": mode, "probes": probes,
        "trial": trial, "threads": 1,
        **metrics,
        "peak_rss_mb": _parse_peak_rss_mb(stderr),
        "wall_s":      round(wall_s, 2),
    }


def run_tapeann(modes):
    done = _load_done(TAPE_CSV, ["mode", "probes", "trial"])
    pending = [
        (mode, probes, trial)
        for mode in modes
        for probes in TAPE_PROBES
        for trial in range(1, TRIALS + 1)
        if (mode, str(probes), str(trial)) not in done
    ]

    _section(f"TAPEANN sweep  —  {len(pending)} runs pending  ({len(done)} already done)")

    run_times = []
    for run_num, (mode, probes, trial) in enumerate(pending, 1):
        eta = _fmt_eta(run_times, len(pending) - run_num + 1)
        _run_header(run_num, len(pending),
                    f"TAPEANN  mode={mode}  probes={probes}  trial={trial}/{TRIALS}", eta)

        t0 = time.time()
        row = run_tape_single(probes, mode, trial)
        run_times.append(time.time() - t0)

        if row:
            _append_row(TAPE_CSV, TAPE_COLS, row)
            print(f"\n  ✓  recall10={row['recall10']:.2f}%  recall1={row['recall1']:.2f}%  "
                  f"qps={row['qps']:,.0f}  mean={row['mean_ms']:.3f} ms  "
                  f"rss={row['peak_rss_mb']} MB  wall={row['wall_s']} s")


# ---- DiskANN runner (Rust diskann-benchmark) ----

import json
import tempfile


def _make_diskann_job(L, beamwidth, mode):
    """Build the JSON job dict for diskann-benchmark run."""
    num_nodes = DISKANN_WARM_CACHE_NODES if mode == "warm" else None
    return {
        "search_directories": [],
        "jobs": [
            {
                "type": "disk-index",
                "content": {
                    "source": {
                        "disk-index-source": "Load",
                        "data_type": "float32",
                        "load_path": DISKANN_INDEX_PREFIX,
                    },
                    "search_phase": {
                        "queries":           DISKANN_QUERY,
                        "groundtruth":       DISKANN_GT,
                        "num_threads":       1,
                        "beam_width":        beamwidth,
                        "search_list":       [L],
                        "recall_at":         K,
                        "is_flat_search":    False,
                        "distance":          "squared_l2",
                        "vector_filters_file": None,
                        "num_nodes_to_cache": num_nodes,
                        "search_io_limit":   None,
                    },
                },
            }
        ],
    }


def _parse_diskann_result(result_json_path):
    """Parse diskann-benchmark JSON output; return first search_results_per_l entry."""
    with open(result_json_path) as f:
        data = json.load(f)
    # Checkpoint format: list of {input: ..., results: {build: ..., search: DiskSearchStats}}
    if not data:
        return None
    search = data[0].get("results", {}).get("search")
    if not search:
        return None
    rows = search.get("search_results_per_l", [])
    if not rows:
        return None
    r = rows[0]
    return {
        "qps":      float(r["qps"]),
        "mean_us":  float(r["mean_latency"]),
        "p999_us":  float(r["p999_latency"]),
        "mean_ios": float(r["mean_ios"]),
        "recall10": round(float(r["recall"]), 4),   # already 0-100 scale
    }


def run_diskann_single(L, beamwidth, mode, trial):
    log_path = os.path.join(LOGS_DIR, f"diskann_{mode}_W{beamwidth}_L{L}_t{trial}.log")
    os.makedirs(LOGS_DIR, exist_ok=True)

    if mode == "cold":
        drop_caches()

    job = _make_diskann_job(L, beamwidth, mode)

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as jf:
        json.dump(job, jf)
        job_path = jf.name

    result_path = os.path.join(LOGS_DIR, f"diskann_{mode}_W{beamwidth}_L{L}_t{trial}_result.json")
    cmd = _wrap_time([
        DISKANN_BENCH,
        "run",
        "--input-file",  job_path,
        "--output-file", result_path,
    ])
    print(f"  $ {' '.join(cmd)}\n")

    t_start = time.time()
    rc, stdout, stderr = _run_streaming(cmd)
    wall_s = time.time() - t_start

    os.unlink(job_path)

    with open(log_path, "w") as f:
        f.write(stdout + "\n---STDERR---\n" + stderr)

    if rc != 0:
        print(f"\n  [!] diskann-benchmark exited {rc}. Full log: {log_path}")
        return None

    metrics = _parse_diskann_result(result_path)
    if not metrics:
        print(f"\n  [!] Could not parse result JSON. Full log: {log_path}")
        return None

    metrics.update({
        "algo":        "diskann",
        "mode":        mode,
        "L":           L,
        "beamwidth":   beamwidth,
        "trial":       trial,
        "threads":     1,
        "wall_s":      round(wall_s, 2),
        "peak_rss_mb": _parse_peak_rss_mb(stderr),
    })
    return metrics


def run_diskann(modes):
    done = _load_done(DISKANN_CSV, ["mode", "L", "beamwidth", "trial"])
    pending = [
        (mode, bw, l, trial)
        for mode in modes
        for bw in DISKANN_BEAMWIDTH
        for l in DISKANN_L_SEARCH
        for trial in range(1, TRIALS + 1)
        if (mode, str(l), str(bw), str(trial)) not in done
    ]
    total = len(pending)

    _section(f"DiskANN sweep  —  {total} runs pending  ({len(done)} already done)")

    run_times = []
    for run_num, (mode, bw, L, trial) in enumerate(pending, 1):
        eta = _fmt_eta(run_times, total - run_num + 1)
        _run_header(run_num, total,
                    f"DiskANN  mode={mode}  W={bw}  L={L}  trial={trial}/{TRIALS}", eta)

        t0 = time.time()
        row = run_diskann_single(L, bw, mode, trial)
        run_times.append(time.time() - t0)

        if row:
            _append_row(DISKANN_CSV, DISKANN_COLS, row)
            print(f"\n  ✓  recall={row['recall10']:.2f}%  QPS={row['qps']:,.0f}  "
                  f"mean={row['mean_us']/1000:.2f} ms  rss={row['peak_rss_mb']} MB")


# ---- Index size reporting ----

def _file_size_mb(path):
    try:
        return round(os.path.getsize(path) / (1024 * 1024), 1)
    except OSError:
        return None

def log_index_sizes():
    """Record on-disk footprint of each index once per sweep."""
    os.makedirs(RESULTS_DIR, exist_ok=True)
    lines = ["# Index on-disk sizes (MB)  —  captured " +
             time.strftime("%Y-%m-%d %H:%M:%S")]

    tape_files = {
        "index_tape.bin":     os.path.join(TAPE_DATA, "index_tape.bin"),
        "centroids.bin":      os.path.join(TAPE_DATA, "centroids.bin"),
        "segment_table.json": os.path.join(TAPE_DATA, "segment_table.json"),
        "global_mean.bin":    os.path.join(TAPE_DATA, "global_mean.bin"),
    }
    tape_total = 0.0
    lines.append("[TAPEANN]")
    for name, path in tape_files.items():
        sz = _file_size_mb(path)
        lines.append(f"  {name:<22} {sz if sz is not None else 'missing'} MB")
        if sz is not None:
            tape_total += sz
    lines.append(f"  TOTAL                  {tape_total:.1f} MB")

    lines.append("[DiskANN]")
    diskann_total = 0.0
    idx_dir = os.path.dirname(DISKANN_INDEX_PREFIX)
    prefix  = os.path.basename(DISKANN_INDEX_PREFIX)
    if os.path.isdir(idx_dir):
        for fname in sorted(os.listdir(idx_dir)):
            if fname.startswith(prefix):
                sz = _file_size_mb(os.path.join(idx_dir, fname))
                lines.append(f"  {fname:<40} {sz} MB")
                if sz is not None:
                    diskann_total += sz
    lines.append(f"  TOTAL                                    {diskann_total:.1f} MB")

    text = "\n".join(lines) + "\n"
    with open(INDEX_SIZES, "w") as f:
        f.write(text)
    print(text)


# ---- Entry point ----

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--algo", default="all", choices=["tapeann", "diskann", "all"])
    ap.add_argument("--mode", default="all", choices=["cold", "warm", "all"])
    ap.add_argument("--build", action="store_true", help="Build indices then exit")
    args = ap.parse_args()

    if args.build:
        build_tapeann()
        return

    tape_modes    = (TAPE_CACHE_MODES if args.mode == "all"
                     else {"cold": ["direct", "drop_once"], "warm": ["cache"]}[args.mode])
    diskann_modes = (["cold", "warm"] if args.mode == "all" else [args.mode])

    log_index_sizes()

    if args.algo in ("tapeann", "all"):
        run_tapeann(tape_modes)
    if args.algo in ("diskann", "all"):
        run_diskann(diskann_modes)

    _hr("═")
    print("  Benchmark complete.  Results in bench/results/")
    _hr("═")


if __name__ == "__main__":
    main()
