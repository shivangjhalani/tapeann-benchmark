"""
Analysis and plotting for TAPEANN vs DiskANN benchmark results.

Usage:  python bench/analyze.py

Reads:  bench/results/tapeann.csv  bench/results/diskann.csv
Writes: bench/plots/*.png  bench/results/summary.md
"""

import os
import sys
import textwrap

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from configs.grid import RESULTS_DIR, PLOTS_DIR

TAPE_CSV    = os.path.join(RESULTS_DIR, "tapeann.csv")
DISKANN_CSV = os.path.join(RESULTS_DIR, "diskann.csv")


# ---- Load & normalise ----

def load_tape():
    df = pd.read_csv(TAPE_CSV)
    df["recall"] = df["recall10"] / 100.0
    df["latency_ms"] = df["mean_ms"]
    df["qps"] = 10_000 / (df["mean_ms"] / 1000 * 10_000)   # 10k queries / total_s
    df["label"] = "TAPEANN " + df["mode"].map({
        "direct":    "(cold/O_DIRECT)",
        "drop_once": "(cold/drop_once)",
        "cache":     "(warm/cache)",
    })
    return df


def load_diskann():
    df = pd.read_csv(DISKANN_CSV)
    df["recall"] = df["recall10"] / 100.0
    df["latency_ms"] = df["mean_us"] / 1000.0
    df["label"] = "DiskANN " + df["mode"].map({"cold": "(cold)", "warm": "(warm)"})
    return df


# ---- Pareto frontier ----

def pareto_front(xs, ys, higher_x=True, lower_y=True):
    """Return indices on the Pareto frontier (maximise x, minimise y)."""
    pts = list(zip(xs, ys, range(len(xs))))
    pts.sort(key=lambda p: (-p[0] if higher_x else p[0]))
    frontier = []
    best_y = float("inf") if lower_y else float("-inf")
    for x, y, i in pts:
        if lower_y and y < best_y:
            best_y = y
            frontier.append(i)
        elif not lower_y and y > best_y:
            best_y = y
            frontier.append(i)
    return sorted(frontier)


# ---- Plots ----

COLORS = {
    "TAPEANN (cold/O_DIRECT)": "#e15759",
    "TAPEANN (warm/cache)":    "#f28e2b",
    "DiskANN (cold)":          "#4e79a7",
    "DiskANN (warm)":          "#76b7b2",
}
MARKERS = {
    "TAPEANN (cold/O_DIRECT)": "o",
    "TAPEANN (warm/cache)":    "s",
    "DiskANN (cold)":          "^",
    "DiskANN (warm)":          "D",
}


def _plot_recall_vs_y(groups, y_col, y_label, fname, log_y=False):
    fig, ax = plt.subplots(figsize=(8, 5))
    for label, df in groups.items():
        sub = df.sort_values("recall")
        # Draw Pareto frontier as solid line, other points as faded dots
        fi = pareto_front(sub["recall"].values, sub[y_col].values,
                          higher_x=True, lower_y=(y_col != "qps"))
        pf = sub.iloc[fi]
        ax.scatter(sub["recall"], sub[y_col],
                   color=COLORS.get(label, "grey"),
                   marker=MARKERS.get(label, "o"),
                   alpha=0.35, s=30)
        ax.plot(pf["recall"].values, pf[y_col].values,
                color=COLORS.get(label, "grey"),
                marker=MARKERS.get(label, "o"),
                label=label, linewidth=1.8, markersize=6)
    ax.set_xlabel("Recall@10", fontsize=12)
    ax.set_ylabel(y_label, fontsize=12)
    ax.set_title(f"Recall@10 vs {y_label}", fontsize=13)
    if log_y:
        ax.set_yscale("log")
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)
    os.makedirs(PLOTS_DIR, exist_ok=True)
    path = os.path.join(PLOTS_DIR, fname)
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"[+] Saved {path}")


def make_plots(tape_df, diskann_df):
    # Split into (label -> sub-df) groups
    groups = {}
    for label, sub in tape_df.groupby("label"):
        groups[label] = sub
    for label, sub in diskann_df.groupby("label"):
        groups[label] = sub

    _plot_recall_vs_y(groups, "latency_ms", "Mean Latency (ms)",
                      "recall_vs_latency.png", log_y=True)
    _plot_recall_vs_y(groups, "qps", "QPS",
                      "recall_vs_qps.png", log_y=False)

    # IOs/query — only DiskANN reports it natively; TAPEANN may have ios_per_q
    io_groups = {}
    if "mean_ios" in diskann_df.columns:
        for label, sub in diskann_df.groupby("label"):
            io_groups[label] = sub.rename(columns={"mean_ios": "ios"})
    tape_ios = tape_df[tape_df["ios_per_q"] != "n/a"].copy()
    if not tape_ios.empty:
        tape_ios["ios"] = tape_ios["ios_per_q"].astype(float)
        for label, sub in tape_ios.groupby("label"):
            io_groups[label] = sub
    if io_groups:
        _plot_recall_vs_y(io_groups, "ios", "Mean IOs / Query",
                          "recall_vs_ios.png", log_y=False)


# ---- Summary table at fixed recall points ----

def _interpolate_at_recall(df, recall_targets, y_cols):
    rows = []
    df = df.sort_values("recall")
    for r in recall_targets:
        above = df[df["recall"] >= r]
        if above.empty:
            row = {"recall_target": f"{r*100:.0f}%"}
            for c in y_cols:
                row[c] = "N/A"
            rows.append(row)
            continue
        # Pick closest point at or above target
        best = above.iloc[0]
        row = {"recall_target": f"{r*100:.0f}%",
               "actual_recall": f"{best['recall']*100:.2f}%"}
        for c in y_cols:
            row[c] = best[c] if c in best else "N/A"
        rows.append(row)
    return pd.DataFrame(rows)


def make_summary(tape_df, diskann_df):
    RECALL_TARGETS = [0.90, 0.95, 0.99]

    lines = ["# TAPEANN vs DiskANN — SIFT10M Benchmark Summary\n"]

    # drop_once matches DiskANN "cold" (both drop page cache once then measure).
    # "direct" uses O_DIRECT on every query — stricter but a different methodology.
    for mode_pair in [("drop_once", "cold"), ("cache", "warm")]:
        tape_mode, diskann_mode = mode_pair
        lines.append(f"\n## Cache mode: TAPEANN={tape_mode}  DiskANN={diskann_mode}\n")

        t = tape_df[tape_df["mode"] == tape_mode].copy()
        # Average across trials (recall is deterministic; latency/qps are averaged)
        t = t.groupby("probes", as_index=False)[["recall", "latency_ms", "qps"]].mean()

        d = diskann_df[diskann_df["mode"] == diskann_mode].copy()
        # For DiskANN pick best (lowest latency) per recall point
        d = d.sort_values("latency_ms").drop_duplicates(subset=["recall"], keep="first")

        for algo, df, y_cols in [
            ("TAPEANN", t, ["latency_ms", "qps", "probes"]),
            ("DiskANN", d, ["latency_ms", "qps", "mean_ios"]),
        ]:
            lines.append(f"### {algo}\n")
            summary = _interpolate_at_recall(df, RECALL_TARGETS, y_cols)
            lines.append(summary.to_markdown(index=False))
            lines.append("\n")

    # Caveats
    lines.append(textwrap.dedent("""
    ## Notes

    - TAPEANN is single-threaded. DiskANN run with `-T 1` for apples-to-apples.
      DiskANN's real multi-thread QPS is significantly higher.
    - Cold runs: `sync && echo 3 > /proc/sys/vm/drop_caches` before each run, then
      queries are issued (page cache warms during the run). Both TAPEANN drop_once and
      DiskANN cold use this methodology. TAPEANN direct (O_DIRECT every query) is shown
      in plots for reference but is a stricter / different cold model.
    - DiskANN recall ceiling may be <1.0 due to PQ compression at the chosen `-B` budget.
    - Ground truth computed via FAISS `IndexFlatL2` on float32 base vectors.
    - SIFT10M = first 10M vectors of BIGANN (`bigann_base.bvecs`).
    """))

    os.makedirs(RESULTS_DIR, exist_ok=True)
    path = os.path.join(RESULTS_DIR, "summary.md")
    with open(path, "w") as f:
        f.write("\n".join(lines))
    print(f"[+] Saved {path}")


# ---- Entry point ----

def main():
    missing = [p for p in (TAPE_CSV, DISKANN_CSV) if not os.path.exists(p)]
    if missing:
        print(f"[!] Missing result files: {missing}")
        print("    Run  python bench/run_bench.py  first.")
        sys.exit(1)

    tape_df    = load_tape()
    diskann_df = load_diskann()

    print(f"[*] TAPEANN rows: {len(tape_df)}  DiskANN rows: {len(diskann_df)}")

    make_plots(tape_df, diskann_df)
    make_summary(tape_df, diskann_df)
    print("\n[+] Analysis complete.")


if __name__ == "__main__":
    main()
