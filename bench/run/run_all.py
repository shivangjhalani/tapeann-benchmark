"""
Unified benchmark runner.

Iterates:  datasets × variants × modes × param_grid × trials
Emits one row per trial to bench/results/runs.csv (schema in grid.RUNS_COLS).

Resumable: re-running skips any (algo, dataset, variant, mode, ram_cap_bytes,
params, threads, trial) that already has a row.

Modes:
  cold_strict    — TAPE uses O_DIRECT, DiskANN uses drop_caches before run
                    (DiskANN can't go truly O_DIRECT without source changes; this
                    is the closest approximation.)
  cold_start     — drop_caches once, run with page cache allowed to warm
  warm_steady    — no drop_caches, binary does its own warm-up
  ram_capped_50  — drop_caches + systemd-run MemoryMax = 50% of disk-resident index
  ram_capped_25  — drop_caches + systemd-run MemoryMax = 25% of disk-resident index

Usage:
  python bench/run/run_all.py                       # full sweep
  python bench/run/run_all.py --dry-run             # print matrix, don't run
  python bench/run/run_all.py --limit 5             # run only first 5 pending
  python bench/run/run_all.py --modes cold_start warm_steady
  python bench/run/run_all.py --variants tape_int8  # subset
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from configs.grid import (
    DATASETS, DISKANN_VARIANTS, TAPE_VARIANTS, MODES, ACTIVE_MODES,
    ACTIVE_VARIANTS, ACTIVE_DATASETS, TAPE_PROBES, DISKANN_L_SEARCH,
    DISKANN_BEAMWIDTH, THREADS_DEFAULT, THREADS_SWEEP, THREAD_SWEEP_PARAMS,
    TRIALS, K,
    DISKANN_BENCH, GT_DIR, DISKANN_DATA, LOGS_DIR,
    variant_index_dir,
)

# DiskANN reads one 4 KB sector per IO. Used to estimate the application-level
# bytes/query (comparable to TAPE's bytes_per_query_app, which the binary
# emits directly).
DISKANN_SECTOR_BYTES = 4096
from run.runner_common import (
    drop_caches, wrap_time, wrap_ram_cap, run_measured,
    load_done_keys, make_resume_key, append_run_row,
    commit_sha, largest_file_bytes,
)

# ─── Mode helpers ───────────────────────────────────────────────────────────

def compute_ram_cap_bytes(mode_cfg: dict, idx_dir: str, algo: str) -> int | None:
    # ram_cap is an absolute byte count (or None). Same literal budget for both
    # systems — no per-algo baselines, no fraction-of-index formulas.
    return mode_cfg.get("ram_cap") or None


# ─── TAPE runner ────────────────────────────────────────────────────────────

def _parse_tape_csv(stdout: str):
    # CSV line emitted by benchmark_search.cpp (schema v3):
    #   CSV:tapeann,probes,<probes>,recall10,recall1,qps,mean_ms,
    #       p50,p95,p99,p999,ios_per_q,bytes_per_q,simd_avoided
    for line in stdout.splitlines():
        if line.startswith("CSV:tapeann,probes,"):
            p = line.split(",")
            if len(p) < 14: return None
            return {
                "recall10":            float(p[3]),
                "recall1":             float(p[4]),
                "qps":                 float(p[5]),
                "mean_ms":             float(p[6]),
                "p50_ms":              float(p[7]),
                "p95_ms":              float(p[8]),
                "p99_ms":              float(p[9]),
                "p999_ms":             float(p[10]),
                "ios_per_query":       float(p[11]),
                "bytes_per_query_app": float(p[12]),
                "simd_avoided":        int(p[13]),
            }
    return None


def run_tape_one(variant, dataset, mode, probes, trial, ram_cap_bytes, threads):
    idx_dir = variant_index_dir(variant, dataset)
    bench_bin = os.path.join(idx_dir, "benchmark_search")
    if not os.path.exists(bench_bin):
        print(f"  [skip] {bench_bin} missing — run build_tapeann.py first.")
        return None

    mode_cfg = MODES[mode]
    flags = []
    if mode_cfg["o_direct"]:
        flags.append("--direct")
    else:
        flags.append("--cache")
        if mode_cfg["warmup_queries"] == 0:
            flags.append("--no-warmup")
    flags += ["--probes", str(probes)]

    if mode_cfg["drop_caches"]:
        drop_caches()

    cmd = wrap_time([bench_bin, *flags])
    cmd = wrap_ram_cap(cmd, ram_cap_bytes)

    log_path = os.path.join(LOGS_DIR,
        f"tape_{variant}_{dataset}_{mode}_p{probes}_t{trial}.log")
    res = run_measured(cmd, cwd=idx_dir, log_path=log_path)
    if res["rc"] != 0:
        print(f"  [!] rc={res['rc']}. See {log_path}")
        return None
    metrics = _parse_tape_csv(res["stdout"])
    if not metrics:
        print(f"  [!] failed to parse TAPE CSV. See {log_path}")
        return None

    return {
        "algo": "tapeann", "dataset": dataset, "variant": variant,
        "mode": mode, "ram_cap_bytes": ram_cap_bytes or "",
        "params_json": json.dumps({"probes": probes}, sort_keys=True),
        "threads": threads, "trial": trial,
        "recall1":  metrics["recall1"],
        "recall10": metrics["recall10"],
        "recall100": "",
        "qps":       metrics["qps"],
        "mean_ms":   metrics["mean_ms"],
        "p50_ms":    metrics["p50_ms"],
        "p95_ms":    metrics["p95_ms"],
        "p99_ms":    metrics["p99_ms"],
        "p999_ms":   metrics["p999_ms"],
        "bytes_read_total":       res["bytes_read_total"],
        "bytes_read_per_query":   round(res["bytes_read_total"] / 10_000, 1),
        "bytes_per_query_app":    round(metrics["bytes_per_query_app"], 1),
        "ios_total":              res["ios_total"],
        "ios_per_query":          metrics["ios_per_query"],
        "simd_distance_calls":    "",
        "simd_avoided":           metrics["simd_avoided"],
        "cpu_user_s":             res["cpu_user_s"],
        "cpu_sys_s":              res["cpu_sys_s"],
        "peak_rss_mb":            res["peak_rss_mb"],
        "wall_s":                 res["wall_s"],
        "commit_sha":             commit_sha(),
    }


# ─── DiskANN runner ─────────────────────────────────────────────────────────

def _make_diskann_job(variant, dataset, L, W, mode_cfg, threads):
    vcfg = DISKANN_VARIANTS[variant]
    idx_dir = variant_index_dir(variant, dataset)
    load_path = os.path.join(idx_dir, f"{variant}__{dataset}")
    num_cache = 200_000 if mode_cfg["warmup_queries"] > 0 else None
    return {
        "search_directories": [],
        "jobs": [{
            "type": "disk-index",
            "content": {
                "source": {
                    "disk-index-source": "Load",
                    "data_type":  vcfg["data_type"],
                    "load_path":  load_path,
                },
                "search_phase": {
                    "queries":     os.path.join(DISKANN_DATA, f"query.{vcfg['base_suffix']}"),
                    "groundtruth": os.path.join(GT_DIR, "gt100.diskann.bin"),
                    "num_threads": threads,
                    "beam_width":  W,
                    "search_list": [L],
                    "recall_at":   K,
                    "is_flat_search":       False,
                    "distance":             "squared_l2",
                    "vector_filters_file":  None,
                    "num_nodes_to_cache":   num_cache,
                    "search_io_limit":      None,
                },
            },
        }],
    }


def _parse_diskann_result(result_json):
    if not os.path.exists(result_json):
        return None
    with open(result_json) as f:
        data = json.load(f)
    if not data: return None
    s = data[0].get("results", {}).get("search")
    if not s: return None
    rows = s.get("search_results_per_l", [])
    if not rows: return None
    r = rows[0]
    # diskann-benchmark reports p95 and p999 in microseconds. p50/p99 aren't
    # emitted by that binary — we leave those blank in runs.csv.
    return {
        "qps":           float(r["qps"]),
        "mean_ms":       float(r["mean_latency"]) / 1000.0,
        "p95_ms":        (float(r["p95_latency"])  / 1000.0) if "p95_latency"  in r else "",
        "p999_ms":       (float(r["p999_latency"]) / 1000.0) if "p999_latency" in r else "",
        "ios_per_query": float(r["mean_ios"]),
        "recall10":      round(float(r["recall"]), 4),
    }


def run_diskann_one(variant, dataset, mode, L, W, trial, ram_cap_bytes, threads):
    idx_dir = variant_index_dir(variant, dataset)
    mode_cfg = MODES[mode]

    if mode_cfg["drop_caches"]:
        drop_caches()

    job = _make_diskann_job(variant, dataset, L, W, mode_cfg, threads)
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as jf:
        json.dump(job, jf); job_path = jf.name
    result_path = os.path.join(LOGS_DIR,
        f"diskann_{variant}_{dataset}_{mode}_L{L}_W{W}_t{trial}_result.json")
    log_path = os.path.join(LOGS_DIR,
        f"diskann_{variant}_{dataset}_{mode}_L{L}_W{W}_t{trial}.log")
    os.makedirs(LOGS_DIR, exist_ok=True)

    cmd = wrap_time([DISKANN_BENCH, "run",
                     "--input-file", job_path,
                     "--output-file", result_path])
    cmd = wrap_ram_cap(cmd, ram_cap_bytes)

    res = run_measured(cmd, log_path=log_path)
    try: os.unlink(job_path)
    except OSError: pass

    if res["rc"] != 0:
        print(f"  [!] rc={res['rc']}. See {log_path}")
        return None

    m = _parse_diskann_result(result_path)
    if not m:
        print(f"  [!] parse failure. See {log_path}")
        return None

    return {
        "algo": "diskann", "dataset": dataset, "variant": variant,
        "mode": mode, "ram_cap_bytes": ram_cap_bytes or "",
        "params_json": json.dumps({"L": L, "W": W}, sort_keys=True),
        "threads": threads, "trial": trial,
        "recall1": "",  "recall10": m["recall10"],  "recall100": "",
        "qps":       m["qps"],
        "mean_ms":   m["mean_ms"],
        "p50_ms":    "",
        "p95_ms":    m["p95_ms"],
        "p99_ms":    "",
        "p999_ms":   m["p999_ms"],
        "bytes_read_total":       res["bytes_read_total"],
        "bytes_read_per_query":   round(res["bytes_read_total"] / 10_000, 1),
        # DiskANN reads one 4 KB sector per IO; app-level bytes/query is
        # therefore mean_ios * 4096. Same semantic as TAPE's directly-emitted
        # bytes_per_query_app so the two are comparable.
        "bytes_per_query_app":    round(m["ios_per_query"] * DISKANN_SECTOR_BYTES, 1),
        "ios_total":              res["ios_total"],
        "ios_per_query":          m["ios_per_query"],
        "simd_distance_calls":    "",  "simd_avoided": "",
        "cpu_user_s":             res["cpu_user_s"],
        "cpu_sys_s":              res["cpu_sys_s"],
        "peak_rss_mb":            res["peak_rss_mb"],
        "wall_s":                 res["wall_s"],
        "commit_sha":             commit_sha(),
    }


# ─── Matrix generator ───────────────────────────────────────────────────────

def iter_jobs(datasets, variants, modes, threads_list, trials,
              thread_sweep=False):
    """Yield dicts describing every pending (or all, caller filters) job.

    When thread_sweep=True, the param grid is replaced by THREAD_SWEEP_PARAMS
    (one canonical operating point per variant) and threads_list is expected
    to be THREADS_SWEEP — isolating the effect of thread count on QPS."""
    for ds in datasets:
        for v in variants:
            algo = "tapeann" if v in TAPE_VARIANTS else "diskann"
            idx_dir = variant_index_dir(v, ds)

            if thread_sweep:
                params_list = THREAD_SWEEP_PARAMS.get(v, [])
                if not params_list:
                    continue
            else:
                if algo == "tapeann":
                    params_list = [{"probes": p} for p in TAPE_PROBES]
                else:
                    params_list = [{"L": L, "W": W}
                                   for L in DISKANN_L_SEARCH
                                   for W in DISKANN_BEAMWIDTH]

            for m in modes:
                mcfg = MODES[m]
                ram_cap = compute_ram_cap_bytes(mcfg, idx_dir, algo)
                for pdict in params_list:
                    for t in range(1, trials + 1):
                        for th in threads_list:
                            yield {
                                "algo": algo, "dataset": ds, "variant": v,
                                "mode": m, "ram_cap_bytes": ram_cap or "",
                                "params_json": json.dumps(pdict, sort_keys=True),
                                "threads": th, "trial": t,
                                "_params": pdict,
                            }


# ─── Analysis pipeline ──────────────────────────────────────────────────────

def _run_analysis():
    """Re-generate aggregated CSVs, plots, and report after a benchmark run."""
    import importlib.util, subprocess

    analyze_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                               "analyze")
    for script in ("pareto.py", "plots.py", "report.py"):
        path = os.path.join(analyze_dir, script)
        if not os.path.exists(path):
            print(f"  [analysis] {script} not found, skipping")
            continue
        print(f"  [analysis] running {script} …")
        result = subprocess.run([sys.executable, path], capture_output=True, text=True)
        if result.returncode != 0:
            print(f"  [!] {script} failed:\n{result.stderr[-2000:]}")
        else:
            if result.stdout.strip():
                print(result.stdout.strip())


# ─── Main ──────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--datasets", nargs="+", default=ACTIVE_DATASETS)
    ap.add_argument("--variants", nargs="+", default=ACTIVE_VARIANTS)
    ap.add_argument("--modes",    nargs="+", default=ACTIVE_MODES)
    ap.add_argument("--threads",  nargs="+", type=int, default=THREADS_DEFAULT)
    ap.add_argument("--trials",   type=int,  default=TRIALS)
    ap.add_argument("--dry-run",  action="store_true")
    ap.add_argument("--limit",    type=int,  default=None)
    ap.add_argument("--thread-sweep", action="store_true",
                    help="Restrict to THREAD_SWEEP_PARAMS operating points and "
                         "sweep over THREADS_SWEEP thread counts (also runs automatically "
                         "as phase 2 of the default run).")
    ap.add_argument("--no-analysis", action="store_true",
                    help="Skip the pareto/plots/report regeneration step at the end.")
    args = ap.parse_args()

    if args.thread_sweep:
        # Manual invocation: run only thread sweep, honour explicit --threads override.
        if args.threads == THREADS_DEFAULT:
            args.threads = THREADS_SWEEP
        done = load_done_keys()
        all_jobs = list(iter_jobs(args.datasets, args.variants, args.modes,
                                  args.threads, args.trials, thread_sweep=True))
        pending = [j for j in all_jobs if make_resume_key(j) not in done]
        print(f"thread-sweep jobs total={len(all_jobs)}  pending={len(pending)}  "
              f"done={len(all_jobs) - len(pending)}")
        if args.limit:
            pending = pending[:args.limit]
        if args.dry_run:
            for j in pending[:25]:
                print(f"  {j['algo']}  {j['variant']}/{j['dataset']}  {j['mode']}  "
                      f"threads={j['threads']}  params={j['params_json']}  trial={j['trial']}")
            if len(pending) > 25:
                print(f"  ... ({len(pending) - 25} more)")
            return
        _execute_jobs(pending)
        if not args.no_analysis:
            _run_analysis()
        return

    # ── Phase 1: full param grid (single-threaded) ───────────────────────────
    grid_jobs = list(iter_jobs(args.datasets, args.variants, args.modes,
                               THREADS_DEFAULT, args.trials, thread_sweep=False))

    # ── Phase 2: DiskANN thread sweep at canonical ~95%-recall op points ─────
    # Runs automatically so a single invocation collects both the full recall
    # curve and the thread-scaling data needed to understand DiskANN throughput.
    sweep_jobs = list(iter_jobs(args.datasets, args.variants, args.modes,
                                THREADS_SWEEP, args.trials, thread_sweep=True))

    all_jobs = grid_jobs + sweep_jobs
    done     = load_done_keys()
    pending  = [j for j in all_jobs if make_resume_key(j) not in done]

    print(f"phase1 (param grid): {len(grid_jobs)} jobs")
    print(f"phase2 (thread sweep): {len(sweep_jobs)} jobs")
    print(f"total={len(all_jobs)}  pending={len(pending)}  "
          f"done={len(all_jobs) - len(pending)}")
    if args.limit:
        pending = pending[: args.limit]

    if args.dry_run:
        for j in pending[:25]:
            print(f"  {j['algo']}  {j['variant']}/{j['dataset']}  {j['mode']}  "
                  f"threads={j['threads']}  cap={j['ram_cap_bytes']}  "
                  f"params={j['params_json']}  trial={j['trial']}")
        if len(pending) > 25:
            print(f"  ... ({len(pending) - 25} more)")
        return

    _execute_jobs(pending)

    if not args.no_analysis:
        print("\n── regenerating analysis ──")
        _run_analysis()


def _execute_jobs(pending):
    for i, j in enumerate(pending, 1):
        t0 = time.time()
        tag = f"[{i}/{len(pending)}] {j['algo']} {j['variant']} {j['mode']} " \
              f"threads={j['threads']} {j['params_json']} trial={j['trial']}"
        print(tag)
        cap = j["ram_cap_bytes"] or None
        if j["algo"] == "tapeann":
            row = run_tape_one(
                variant=j["variant"], dataset=j["dataset"], mode=j["mode"],
                probes=j["_params"]["probes"], trial=j["trial"],
                ram_cap_bytes=cap, threads=j["threads"])
        else:
            row = run_diskann_one(
                variant=j["variant"], dataset=j["dataset"], mode=j["mode"],
                L=j["_params"]["L"], W=j["_params"]["W"], trial=j["trial"],
                ram_cap_bytes=cap, threads=j["threads"])
        if row is not None:
            append_run_row(row)
            dur = time.time() - t0
            print(f"  ✓ {dur:.1f}s  recall10={row['recall10']}  qps={row['qps']}")


if __name__ == "__main__":
    main()
