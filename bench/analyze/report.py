"""
Assemble bench/results/report.md from:
  - bench/results/env.txt
  - bench/results/build_costs.csv
  - bench/results/closest_recall.csv
  - bench/results/plots/*.png
"""

import csv
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from configs.grid import RESULTS_DIR, BUILD_COSTS_CSV, PLOTS_DIR, ENV_TXT, ACTIVE_MODES

# Headline pairing: matched bytes/vector. fp32 and uint8_pq32 are reference only.
HEADLINE_PAIR = [("tapeann", "tape_int8"), ("diskann", "diskann_uint8_pq64")]
REFERENCE_VARIANTS = {"diskann_fp32_pq64", "diskann_uint8_pq32"}

CLOSEST_CSV = os.path.join(RESULTS_DIR, "closest_recall.csv")
OUT_MD      = os.path.join(RESULTS_DIR, "report.md")


def _read_csv(path):
    if not os.path.exists(path): return []
    with open(path) as f:
        return list(csv.DictReader(f))


def _md_table(rows, cols, headers=None):
    if not rows: return "(no rows)"
    headers = headers or cols
    lines = ["| " + " | ".join(headers) + " |",
             "|" + "|".join(["---"] * len(headers)) + "|"]
    for r in rows:
        lines.append("| " + " | ".join(str(r.get(c, "")) for c in cols) + " |")
    return "\n".join(lines)


def build_cost_section():
    rows = _read_csv(BUILD_COSTS_CSV)
    if not rows:
        return "_no build_costs.csv yet — run build_tapeann.py / build_diskann.py_"
    for r in rows:
        gb = int(r.get("index_total_bytes") or 0) / 1e9
        r["size_gb"] = f"{gb:.2f}"
    return _md_table(
        rows,
        cols=["algo", "variant", "dataset", "build_wall_s",
              "build_peak_rss_mb", "size_gb", "timestamp"],
        headers=["algo", "variant", "dataset", "wall_s",
                 "peak_rss_mb", "idx_GB", "built_at"],
    )


def head_to_head_section():
    """Matched-bytes headline: tape_int8 vs diskann_uint8_pq64 only.
    One sub-table per (dataset, mode); rows = recall targets; columns =
    (target, tape recall/qps/ms/bytes, diskann recall/qps/ms/bytes, qps_ratio).
    Always uses threads=1 for both sides so the comparison is apples-to-apples."""
    rows = _read_csv(CLOSEST_CSV)
    if not rows:
        return "_no closest_recall.csv yet — run pareto.py_"
    rows = [r for r in rows if r["mode"] in ACTIVE_MODES]
    # Restrict to single-threaded results only so DiskANN's multi-thread sweep
    # data doesn't inflate its QPS relative to TapeANN's always-single-threaded runs.
    rows = [r for r in rows if str(r.get("threads", "1")) == "1"]
    want = {(a, v) for (a, v) in HEADLINE_PAIR}
    rows = [r for r in rows if (r["algo"], r["variant"]) in want]
    if not rows:
        return "_no head-to-head rows — check that both tape_int8 and diskann_uint8_pq64 have runs_"

    by_key = {}
    for r in rows:
        k = (r["dataset"], r["mode"], float(r["target_recall"]))
        by_key.setdefault(k, {})[r["variant"]] = r

    chunks = []
    seen = set()
    for (ds, mode, t) in sorted(by_key.keys()):
        if (ds, mode) in seen:
            continue
        seen.add((ds, mode))
        chunks.append(f"### `{ds}` · mode=`{mode}`\n")
        hdr = ["target", "tape achieved", "tape qps", "tape ms", "tape B/q (app)",
               "diskann achieved", "diskann qps", "diskann ms", "diskann B/q (app)",
               "qps ratio (tape/diskann)"]
        lines = ["| " + " | ".join(hdr) + " |",
                 "|" + "|".join(["---"] * len(hdr)) + "|"]
        for target in (85.0, 90.0, 95.0, 97.0, 99.0):
            pair = by_key.get((ds, mode, target), {})
            t_row = pair.get("tape_int8")
            d_row = pair.get("diskann_uint8_pq64")
            if not (t_row and d_row):
                continue
            try:
                ratio = f"{float(t_row['qps']) / float(d_row['qps']):.2f}×"
            except (ValueError, ZeroDivisionError):
                ratio = "—"
            lines.append("| " + " | ".join([
                f"{target:.0f}",
                t_row["achieved_recall"], t_row["qps"], t_row["mean_ms"], t_row["bytes_per_query_app"],
                d_row["achieved_recall"], d_row["qps"], d_row["mean_ms"], d_row["bytes_per_query_app"],
                ratio,
            ]) + " |")
        chunks.append("\n".join(lines))
        chunks.append("")
    return "\n".join(chunks)


def recall_table_section():
    rows = _read_csv(CLOSEST_CSV)
    if not rows:
        return "_no closest_recall.csv yet — run pareto.py_"
    rows = [r for r in rows if r["mode"] in ACTIVE_MODES]
    # Only show single-threaded results here; multi-thread scaling is in the
    # thread-sweep section, and duplicate rows (one per thread count) for the
    # same recall target are confusing when the threads column isn't shown.
    rows = [r for r in rows if str(r.get("threads", "1")) == "1"]
    for r in rows:
        if r["variant"] in REFERENCE_VARIANTS:
            r["variant"] = r["variant"] + " (ref)"
    rows = sorted(rows, key=lambda r: (r["dataset"], r["mode"],
                                       float(r["target_recall"]),
                                       r["algo"], r["variant"]))
    by_mode = {}
    for r in rows:
        by_mode.setdefault((r["dataset"], r["mode"]), []).append(r)
    chunks = []
    for (ds, m), rs in by_mode.items():
        chunks.append(f"### `{ds}` · mode=`{m}`\n")
        chunks.append(_md_table(rs,
            cols=["target_recall", "algo", "variant",
                  "achieved_recall", "mean_ms", "p95_ms", "p999_ms", "qps",
                  "bytes_per_query_app", "ios_per_query", "params_json", "n_trials"],
            headers=["target", "algo", "variant", "achieved",
                     "mean_ms", "p95_ms", "p999_ms", "qps",
                     "B/q (app)", "ios/q", "params", "n"]))
        chunks.append("")
    return "\n".join(chunks)


def thread_sweep_section():
    """Emit a QPS-vs-threads table from aggregated.csv, filtered to rows
    whose params match THREAD_SWEEP_PARAMS."""
    agg_path = os.path.join(RESULTS_DIR, "aggregated.csv")
    rows = _read_csv(agg_path)
    if not rows:
        return "_no aggregated.csv yet_"
    from configs.grid import THREAD_SWEEP_PARAMS
    wanted_by_variant = {
        v: {json.dumps(p, sort_keys=True) for p in plist}
        for v, plist in THREAD_SWEEP_PARAMS.items()
    }
    sweep = [r for r in rows
             if r.get("variant") in wanted_by_variant
             and r.get("params_json") in wanted_by_variant[r["variant"]]]
    # Only show rows where threads > 1 exists (otherwise nothing to sweep)
    thread_vals = sorted({int(r["threads"]) for r in sweep if r.get("threads")})
    if len(thread_vals) < 2:
        return "_no thread-sweep data — run `run_all.py --thread-sweep`_"

    out = []
    by_mode = {}
    for r in sweep:
        by_mode.setdefault((r["dataset"], r["mode"]), []).append(r)
    for (ds, m), rs in by_mode.items():
        out.append(f"### `{ds}` · mode=`{m}`\n")
        out.append(_md_table(
            sorted(rs, key=lambda r: (r["variant"], int(r["threads"]))),
            cols=["variant", "threads", "params_json",
                  "recall10_median", "mean_ms_median", "qps_median", "n_trials"],
            headers=["variant", "threads", "params",
                     "recall@10", "mean_ms", "qps", "n"]))
        out.append("")
    return "\n".join(out)


TAKEAWAYS = """\
> Numbers below compare TapeANN (single-threaded) against single-threaded \
DiskANN `uint8_pq64` unless noted. Multi-thread DiskANN numbers are in the \
thread-scaling section.

**1. TapeANN wins at 85–90 % and 97 % recall (1-thread comparison).**
At 90 % recall TapeANN is ~1.9–2× faster than 1-thread DiskANN across all \
modes (warm, 1.5 GB cap, 3 GB cap). It also leads at 85 % (~1.05–1.25×) and \
97 % (~1.12–1.24×).

**2. 95 % recall is a consistent crossover loss.**
TapeANN loses to DiskANN at 95 % in every mode (~0.54–0.63×). The jump from \
30 probes (90 % target) to 60 probes (95 % target) halves QPS while adding \
only 5 recall points — a probe-count cliff that is the main weak spot in the \
recall curve.

**3. 99 % recall is a collapse.**
TapeANN needs 1000 probes to reach ~98.9 % recall: 13 QPS (1.5 GB cap), \
29 QPS (3 GB cap), 36 QPS (warm). DiskANN achieves the same recall at \
417–495 QPS (1-thread) — 15–38× faster. High-recall workloads are not viable \
with the current probe mechanism.

**4. RAM cap matters significantly for TapeANN at high probe counts.**
Going from 1.5 GB → 3 GB, TapeANN at 99 % recall improves from 13 → 29 QPS \
(+2.2×); at 95 % from 428 → 460 QPS (+7 %). At 85–90 % the two caps are \
nearly equivalent. DiskANN sees minimal change across caps. TapeANN's large \
I/O footprint (157 MB/query at 1000 probes) makes it highly sensitive to page \
cache size at high probe counts.

**5. I/O amplification is extreme and worsens rapidly with probes.**
TapeANN reads ~3.6 MB/query at 85 % recall vs DiskANN's 125 KB (29×); at \
99 % this is 157 MB/query (420×). This is the root cause of the 99 %-recall \
collapse and limits viability in storage-bound deployments.

**6. DiskANN multi-threading changes the picture entirely.**
At 16 threads DiskANN reaches 8073 QPS warm (95 % recall) vs TapeANN's \
516 QPS — a 15.6× gap. At 1 thread DiskANN is only 1.85× ahead (953 vs 516). \
Threading is the dominant factor: a multi-threaded DiskANN deployment dominates \
TapeANN at every recall target.

**7. "Higher recall = lower latency" in the plots is expected and not a contradiction.**
The recall-vs-latency and recall-vs-QPS curves show latency *decreasing* as recall \
increases over certain ranges. This happens because the plots sweep across multiple \
(L, W) parameter pairs, not just L at fixed W. Configurations with low beamwidth \
(W=1) and low L land at low recall but high latency — beam search with W=1 is \
sequential and cache-unfriendly. Configurations with high beamwidth (W=4) at \
slightly higher L reach better recall with *lower* latency because the 4 parallel \
beams amortize memory access costs more efficiently. The downward-sloping segment \
of a curve therefore represents dominated operating points — configurations that \
are both slower *and* less accurate than a nearby W=4 point. In practice, only \
the rightmost (Pareto-optimal) end of each curve should be used.
"""


def takeaways_section():
    return TAKEAWAYS


def plots_section():
    if not os.path.isdir(PLOTS_DIR):
        return "_no plots/_"
    pngs = sorted(f for f in os.listdir(PLOTS_DIR) if f.endswith(".png"))
    if not pngs:
        return "_no PNGs in plots/ yet — run plots.py_"
    return "\n\n".join(f"![{p}](plots/{p})" for p in pngs)


def env_section():
    if not os.path.exists(ENV_TXT):
        return "_env.txt missing — run bench/prep/env_capture.sh_"
    with open(ENV_TXT) as f:
        body = f.read()
    return "```\n" + body.strip() + "\n```"


def main():
    parts = []
    parts.append("# TAPEANN vs DiskANN — benchmark report\n")
    parts.append("## Environment\n"        + env_section())
    parts.append("\n## Build costs\n"      + build_cost_section())
    parts.append("\n## Head-to-head (matched bytes/vector)\n"
                 + "`tape_int8` vs `diskann_uint8_pq64` at fixed recall targets. "
                 + "Both systems store 1 byte per dimension in the vector store; "
                 + "other DiskANN variants are reported as reference only.\n\n"
                 + head_to_head_section())
    parts.append("\n## All operating points (closest to recall target)\n"
                 + "Includes reference variants `diskann_fp32_pq64 (ref)` and "
                 + "`diskann_uint8_pq32 (ref)`. "
                 + "Each cell is the median across trials.\n\n"
                 + recall_table_section())
    parts.append("\n## Thread scaling (DiskANN; TapeANN is single-threaded)\n"
                 + "Fixed operating point ≈ 95% recall; threads is the only "
                 + "varied dimension. Shows DiskANN's multi-core throughput scaling "
                 + "relative to TapeANN's single-threaded baseline.\n\n"
                 + thread_sweep_section())
    parts.append("\n## Pareto plots\n"     + plots_section())
    parts.append("\n## Takeaways\n"        + takeaways_section())
    with open(OUT_MD, "w") as f:
        f.write("\n".join(parts) + "\n")
    print(f"→ {OUT_MD}")


if __name__ == "__main__":
    main()
