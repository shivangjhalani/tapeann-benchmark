"""
TapeANN-focused companion plots that highlight where the clustering-based
design outperforms graph-based DiskANN. Reads the same aggregated.csv /
closest_recall.csv / runs.csv the other analyze scripts emit.

Emits into PLOTS_DIR:
  - recall_vs_qps_zoom__<ds>__<mode>.png   (recall ∈ [75,97])
  - qps_speedup_bars__<ds>.png             (tape/diskann at recall targets)
  - avg_read_size__<ds>__<mode>.png        (bytes per I/O vs recall)
  - tail_ratio__<ds>__<mode>.png           (p999/mean vs recall)
  - cache_sensitivity__<ds>.png            (QPS across modes, per recall target)
  - tape_probe_curve__<ds>.png             (recall & QPS vs probes)
  - io_amplification__<ds>__<mode>.png     (physical-vs-app bytes, cache win)
"""

import csv
import json
import os
import sys
from collections import defaultdict

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from configs.grid import RESULTS_DIR, PLOTS_DIR

AGG = os.path.join(RESULTS_DIR, "aggregated.csv")
CLOSEST = os.path.join(RESULTS_DIR, "closest_recall.csv")
RUNS = os.path.join(RESULTS_DIR, "runs.csv")

TAPE_COLOR = "#d7263d"
DISKANN_COLOR = "#1b4079"
MODE_ORDER = ["warm", "ram_capped_3gb", "ram_capped_1p5gb"]
MODE_LABEL = {"warm": "warm",
              "ram_capped_3gb": "RAM-cap 3 GB",
              "ram_capped_1p5gb": "RAM-cap 1.5 GB"}


def _f(x):
    try: return float(x) if x not in (None, "") else None
    except ValueError: return None


def load(path):
    if not os.path.exists(path):
        return []
    with open(path) as fh:
        return list(csv.DictReader(fh))


def _save(fig, name):
    os.makedirs(PLOTS_DIR, exist_ok=True)
    out = os.path.join(PLOTS_DIR, name)
    fig.tight_layout()
    fig.savefig(out, dpi=140)
    plt.close(fig)
    print(f"  → {out}")


# ---------- 1. zoomed recall vs QPS (highlights the 85–97% wins) ----------

def plot_zoomed_qps(agg, dataset):
    single = [r for r in agg if r["dataset"] == dataset
              and str(r.get("threads", "1")) == "1"]
    modes = sorted({r["mode"] for r in single})
    for mode in modes:
        rows = [r for r in single if r["mode"] == mode]
        if not rows: continue
        fig, ax = plt.subplots(figsize=(7, 5))
        groups = defaultdict(list)
        for r in rows: groups[(r["algo"], r["variant"])].append(r)
        for (algo, variant), pts in sorted(groups.items()):
            pts = [(p, _f(p["recall10_median"]), _f(p["qps_median"]))
                   for p in pts]
            pts = [t for t in pts if t[1] is not None and t[2] is not None
                   and 75.0 <= t[1] <= 97.5]
            if not pts: continue
            pts.sort(key=lambda t: t[1])
            xs = [t[1] for t in pts]; ys = [t[2] for t in pts]
            color = TAPE_COLOR if algo == "tapeann" else DISKANN_COLOR
            ls = "-" if variant in ("tape_int8", "diskann_uint8_pq64") else "--"
            ax.plot(xs, ys, marker="o", linewidth=1.8, linestyle=ls,
                    markersize=5, color=color, alpha=0.9,
                    label=f"{algo}/{variant}")
        ax.set_xlabel("recall@10 (%)")
        ax.set_ylabel("QPS (single-threaded)")
        ax.set_title(f"{dataset} · {MODE_LABEL.get(mode, mode)} · zoom 75–97 %")
        ax.grid(True, alpha=0.3)
        ax.legend(fontsize=8, loc="best")
        _save(fig, f"recall_vs_qps_zoom__{dataset}__{mode}.png")


# ---------- 2. QPS speedup bar chart ----------

def plot_speedup_bars(closest, dataset):
    rows = [r for r in closest if r["dataset"] == dataset
            and str(r.get("threads", "1")) == "1"
            and r["variant"] in ("tape_int8", "diskann_uint8_pq64")]
    if not rows: return
    targets = sorted({_f(r["target_recall"]) for r in rows})
    modes = [m for m in MODE_ORDER if any(r["mode"] == m for r in rows)]
    fig, ax = plt.subplots(figsize=(8.5, 5))
    width = 0.25
    x = np.arange(len(targets))
    for i, mode in enumerate(modes):
        ratios = []
        for t in targets:
            tape = next((r for r in rows if r["mode"] == mode
                         and r["variant"] == "tape_int8"
                         and _f(r["target_recall"]) == t), None)
            dk = next((r for r in rows if r["mode"] == mode
                       and r["variant"] == "diskann_uint8_pq64"
                       and _f(r["target_recall"]) == t), None)
            if tape and dk and _f(dk["qps"]):
                ratios.append(_f(tape["qps"]) / _f(dk["qps"]))
            else:
                ratios.append(0.0)
        bars = ax.bar(x + (i - 1) * width, ratios, width,
                      label=MODE_LABEL.get(mode, mode))
        for b, r in zip(bars, ratios):
            if r > 0:
                ax.text(b.get_x() + b.get_width() / 2, r + 0.03,
                        f"{r:.2f}×", ha="center", va="bottom", fontsize=8)
    ax.axhline(1.0, color="black", linestyle=":", linewidth=1)
    ax.set_xticks(x, [f"{int(t)}%" for t in targets])
    ax.set_xlabel("recall target")
    ax.set_ylabel("QPS ratio (tape_int8 ÷ diskann_uint8_pq64)")
    ax.set_title(f"{dataset} · single-thread speedup (≥1 means TapeANN wins)")
    ax.grid(True, axis="y", alpha=0.3)
    ax.legend(fontsize=9)
    _save(fig, f"qps_speedup_bars__{dataset}.png")


# ---------- 3. average read size vs recall ----------

def plot_avg_read_size(agg, dataset):
    single = [r for r in agg if r["dataset"] == dataset
              and str(r.get("threads", "1")) == "1"]
    modes = sorted({r["mode"] for r in single})
    for mode in modes:
        rows = [r for r in single if r["mode"] == mode]
        fig, ax = plt.subplots(figsize=(7, 5))
        groups = defaultdict(list)
        for r in rows: groups[(r["algo"], r["variant"])].append(r)
        for (algo, variant), pts in sorted(groups.items()):
            triples = []
            for p in pts:
                rec = _f(p["recall10_median"])
                bpq = _f(p["bytes_per_query_app_median"])
                ios = _f(p["ios_per_query_median"])
                if rec is None or bpq is None or not ios: continue
                triples.append((rec, bpq / ios / 1024.0))  # KB per I/O
            if not triples: continue
            triples.sort()
            xs = [t[0] for t in triples]; ys = [t[1] for t in triples]
            color = TAPE_COLOR if algo == "tapeann" else DISKANN_COLOR
            ls = "-" if variant in ("tape_int8", "diskann_uint8_pq64") else "--"
            ax.plot(xs, ys, marker="o", linestyle=ls, color=color,
                    label=f"{algo}/{variant}", markersize=4, linewidth=1.6)
        ax.set_xlabel("recall@10 (%)")
        ax.set_ylabel("avg KB per I/O (bytes_per_query ÷ ios_per_query)")
        ax.set_yscale("log")
        ax.set_title(f"{dataset} · {MODE_LABEL.get(mode, mode)} · sequential bandwidth proxy")
        ax.grid(True, which="both", alpha=0.3)
        ax.legend(fontsize=8)
        _save(fig, f"avg_read_size__{dataset}__{mode}.png")


# ---------- 4. tail latency ratio ----------

def plot_tail_ratio(agg, dataset):
    single = [r for r in agg if r["dataset"] == dataset
              and str(r.get("threads", "1")) == "1"]
    modes = sorted({r["mode"] for r in single})
    for mode in modes:
        rows = [r for r in single if r["mode"] == mode]
        fig, ax = plt.subplots(figsize=(7, 5))
        groups = defaultdict(list)
        for r in rows: groups[(r["algo"], r["variant"])].append(r)
        for (algo, variant), pts in sorted(groups.items()):
            triples = []
            for p in pts:
                rec = _f(p["recall10_median"])
                mean = _f(p["mean_ms_median"])
                p999 = _f(p["p999_ms_median"])
                if not rec or not mean or not p999: continue
                if 75 <= rec <= 97.5:
                    triples.append((rec, p999 / mean))
            if not triples: continue
            triples.sort()
            xs = [t[0] for t in triples]; ys = [t[1] for t in triples]
            color = TAPE_COLOR if algo == "tapeann" else DISKANN_COLOR
            ls = "-" if variant in ("tape_int8", "diskann_uint8_pq64") else "--"
            ax.plot(xs, ys, marker="o", linestyle=ls, color=color,
                    label=f"{algo}/{variant}", markersize=4, linewidth=1.6)
        ax.set_xlabel("recall@10 (%)")
        ax.set_ylabel("p999 / mean latency ratio (lower = tighter tail)")
        ax.set_title(f"{dataset} · {MODE_LABEL.get(mode, mode)} · tail-latency predictability")
        ax.grid(True, alpha=0.3)
        ax.legend(fontsize=8)
        _save(fig, f"tail_ratio__{dataset}__{mode}.png")


# ---------- 5. cache sensitivity ----------

def plot_cache_sensitivity(closest, dataset):
    rows = [r for r in closest if r["dataset"] == dataset
            and str(r.get("threads", "1")) == "1"
            and r["variant"] in ("tape_int8", "diskann_uint8_pq64")]
    targets = sorted({_f(r["target_recall"]) for r in rows})
    targets = [t for t in targets if t is not None and t <= 97]
    modes = [m for m in MODE_ORDER if any(r["mode"] == m for r in rows)]
    fig, axes = plt.subplots(1, len(targets), figsize=(4 * len(targets), 4.5),
                             sharey=False)
    if len(targets) == 1: axes = [axes]
    for ax, t in zip(axes, targets):
        x = np.arange(len(modes))
        for variant, color in (("tape_int8", TAPE_COLOR),
                               ("diskann_uint8_pq64", DISKANN_COLOR)):
            ys = []
            for m in modes:
                r = next((r for r in rows if r["mode"] == m
                          and r["variant"] == variant
                          and _f(r["target_recall"]) == t), None)
                ys.append(_f(r["qps"]) if r else 0.0)
            ax.plot(x, ys, marker="o", color=color, linewidth=1.8,
                    label=variant)
            for xi, yi in zip(x, ys):
                ax.text(xi, yi, f" {yi:.0f}", fontsize=7, va="bottom")
        ax.set_xticks(x, [MODE_LABEL[m] for m in modes], rotation=20,
                      ha="right", fontsize=8)
        ax.set_title(f"recall ≈ {int(t)} %")
        ax.grid(True, alpha=0.3)
    axes[0].set_ylabel("QPS (single-threaded)")
    axes[-1].legend(fontsize=8, loc="best")
    fig.suptitle(f"{dataset} · cache sensitivity (warm → 3 GB → 1.5 GB)")
    _save(fig, f"cache_sensitivity__{dataset}.png")


# ---------- 6. TapeANN probe curve (recall & QPS vs probes) ----------

def plot_tape_probe_curve(agg, dataset):
    rows = [r for r in agg if r["dataset"] == dataset
            and r["algo"] == "tapeann"
            and str(r.get("threads", "1")) == "1"]
    if not rows: return
    modes = [m for m in MODE_ORDER if any(r["mode"] == m for r in rows)]
    fig, ax = plt.subplots(figsize=(8, 5))
    ax2 = ax.twinx()
    colors = {"warm": "#2a9d8f", "ram_capped_3gb": "#e76f51",
              "ram_capped_1p5gb": "#6a4c93"}
    for mode in modes:
        mr = [r for r in rows if r["mode"] == mode]
        pts = []
        for r in mr:
            try: probes = json.loads(r["params_json"])["probes"]
            except Exception: continue
            rec = _f(r["recall10_median"]); qps = _f(r["qps_median"])
            if rec is None or qps is None: continue
            pts.append((probes, rec, qps))
        if not pts: continue
        pts.sort()
        xs = [p[0] for p in pts]
        recs = [p[1] for p in pts]
        qpss = [p[2] for p in pts]
        c = colors.get(mode, "black")
        ax.plot(xs, recs, marker="o", linestyle="-", color=c,
                label=f"recall · {MODE_LABEL[mode]}", markersize=4)
        ax2.plot(xs, qpss, marker="s", linestyle="--", color=c, alpha=0.6,
                 label=f"QPS · {MODE_LABEL[mode]}", markersize=4)
    ax.set_xscale("log")
    ax2.set_yscale("log")
    ax.set_xlabel("probes (log scale)")
    ax.set_ylabel("recall@10 (%)   [solid]")
    ax2.set_ylabel("QPS (log)   [dashed]")
    ax.set_title(f"{dataset} · TapeANN probe sweep: where the cliff lives")
    ax.grid(True, which="both", alpha=0.3)
    lines, labels = ax.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax.legend(lines + lines2, labels + labels2, fontsize=7, loc="center left")
    _save(fig, f"tape_probe_curve__{dataset}.png")


# ---------- 7. physical vs application bytes — the page-cache win ----------

def plot_io_amplification(runs, dataset):
    """Plot (physical bytes) / (application bytes) per query vs recall.

    < 1.0 means the page cache absorbed reads (same page served multiple
    app-level reads = sequential / cache-friendly access).
    > 1.0 means the OS read more than the app asked for (typical for 4 KB
    random access on a graph index).
    """
    from statistics import median
    rows = [r for r in runs if r["dataset"] == dataset
            and str(r.get("threads", "1")) == "1"
            and r["variant"] in ("tape_int8", "diskann_uint8_pq64")]
    buckets = defaultdict(list)
    for r in rows:
        key = (r["algo"], r["variant"], r["mode"], r["params_json"])
        rec = _f(r["recall10"])
        phys = _f(r["bytes_read_per_query"])
        app = _f(r["bytes_per_query_app"])
        if rec is None or phys is None or app is None or app <= 0 or phys <= 0:
            continue
        buckets[key].append((rec, phys / app))
    medians = {k: (median(a for a, _ in v), median(b for _, b in v))
               for k, v in buckets.items()}
    modes = sorted({k[2] for k in medians})
    for mode in modes:
        fig, ax = plt.subplots(figsize=(7, 5))
        groups = defaultdict(list)
        for k, v in medians.items():
            if k[2] != mode: continue
            groups[(k[0], k[1])].append(v)
        for (algo, variant), pts in sorted(groups.items()):
            pts = [p for p in pts if 75 <= p[0] <= 97.5]
            if not pts: continue
            pts.sort()
            xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
            color = TAPE_COLOR if algo == "tapeann" else DISKANN_COLOR
            ax.plot(xs, ys, marker="o", color=color, linewidth=1.8,
                    markersize=5, label=f"{algo}/{variant}")
        ax.axhline(1.0, color="black", linestyle=":", linewidth=1,
                   label="physical = app")
        ax.set_xlabel("recall@10 (%)")
        ax.set_ylabel("physical bytes / app bytes  (lower = cache-friendly)")
        ax.set_yscale("log")
        ax.set_title(f"{dataset} · {MODE_LABEL.get(mode, mode)} · page-cache effectiveness")
        ax.grid(True, which="both", alpha=0.3)
        ax.legend(fontsize=8)
        _save(fig, f"io_amplification__{dataset}__{mode}.png")


def main():
    agg = load(AGG)
    closest = load(CLOSEST)
    runs = load(RUNS)
    datasets = sorted({r["dataset"] for r in agg}) or ["sift10m"]
    for ds in datasets:
        print(f"[{ds}] promo plots")
        plot_zoomed_qps(agg, ds)
        plot_speedup_bars(closest, ds)
        plot_avg_read_size(agg, ds)
        plot_tail_ratio(agg, ds)
        plot_cache_sensitivity(closest, ds)
        plot_tape_probe_curve(agg, ds)
        plot_io_amplification(runs, ds)


if __name__ == "__main__":
    main()
