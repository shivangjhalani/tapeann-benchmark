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
    (target, tape recall/qps/ms/bytes, diskann recall/qps/ms/bytes, qps_ratio)."""
    rows = _read_csv(CLOSEST_CSV)
    if not rows:
        return "_no closest_recall.csv yet — run pareto.py_"
    rows = [r for r in rows if r["mode"] in ACTIVE_MODES]
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
        hdr = ["target", "tape achieved", "tape qps", "tape ms", "tape B/q",
               "diskann achieved", "diskann qps", "diskann ms", "diskann B/q",
               "qps ratio (tape/diskann)"]
        lines = ["| " + " | ".join(hdr) + " |",
                 "|" + "|".join(["---"] * len(hdr)) + "|"]
        for target in (85.0, 90.0, 95.0):
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
                t_row["achieved_recall"], t_row["qps"], t_row["mean_ms"], t_row["bytes_read_per_query"],
                d_row["achieved_recall"], d_row["qps"], d_row["mean_ms"], d_row["bytes_read_per_query"],
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
                  "achieved_recall", "mean_ms", "qps",
                  "bytes_read_per_query", "ios_per_query", "params_json"],
            headers=["target", "algo", "variant", "achieved",
                     "latency_ms", "qps", "bytes/q", "ios/q", "params"]))
        chunks.append("")
    return "\n".join(chunks)


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
                 + "`diskann_uint8_pq32 (ref)`.\n\n"
                 + recall_table_section())
    parts.append("\n## Pareto plots\n"     + plots_section())
    with open(OUT_MD, "w") as f:
        f.write("\n".join(parts) + "\n")
    print(f"→ {OUT_MD}")


if __name__ == "__main__":
    main()
