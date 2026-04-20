"""
Emit the three headline plots per (dataset, mode) from aggregated.csv:
  - recall_vs_latency.png
  - recall_vs_qps.png
  - recall_vs_bytes_read.png

One curve per (algo, variant). X and Y use Pareto-style step curves
(sorted by recall ascending, keeping only monotonically improving points).
"""

import csv
import os
import sys
from collections import defaultdict

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from configs.grid import RESULTS_DIR, PLOTS_DIR


AGG_CSV = os.path.join(RESULTS_DIR, "aggregated.csv")


def _f(x):
    try: return float(x) if x not in (None, "") else None
    except ValueError: return None


def load_agg():
    if not os.path.exists(AGG_CSV):
        return []
    with open(AGG_CSV) as f:
        return list(csv.DictReader(f))


def group_by(rows, *keys):
    out = defaultdict(list)
    for r in rows:
        out[tuple(r.get(k, "") for k in keys)].append(r)
    return out


def envelope(points, x_key, y_key, minimize_y=True):
    """Return Pareto-optimal (x, y) pairs: higher x is always better; y is
    better when lower (minimize_y=True) or higher (minimize_y=False).

    A point is kept iff no other point has both higher-or-equal x AND
    better-or-equal y.  Algorithm: sort by x descending and keep each point
    whose y is at least as good as the best y seen so far among higher-x
    points — equivalent to sweeping from the high-recall end and keeping
    points that improve the performance frontier."""
    pts = [(p, _f(p[x_key]), _f(p[y_key])) for p in points]
    pts = [(p, x, y) for (p, x, y) in pts if x is not None and y is not None]
    if not pts:
        return []
    pts.sort(key=lambda t: (-t[1], t[2] if minimize_y else -t[2]))
    out = []
    best = None
    for _, x, y in pts:
        if best is None or (minimize_y and y <= best) or (not minimize_y and y >= best):
            out.append((x, y))
            best = y
    out.sort()
    return out


MARKERS = {"tape_int8": "o", "diskann_fp32_pq64": "s",
           "diskann_uint8_pq32": "^", "diskann_uint8_pq64": "D"}


def plot_panel(agg_rows, dataset, mode, y_key, y_label, y_log=False,
               minimize_y=True, fname=None):
    rows = [r for r in agg_rows
            if r.get("dataset") == dataset and r.get("mode") == mode]
    if not rows:
        return

    groups = group_by(rows, "algo", "variant")
    fig, ax = plt.subplots(figsize=(7, 5))

    for (algo, variant), pts in sorted(groups.items()):
        env = envelope(pts, "recall10_median", y_key, minimize_y=minimize_y)
        if not env:
            continue
        xs, ys = zip(*env)
        ax.plot(xs, ys, marker=MARKERS.get(variant, "x"),
                label=f"{algo} / {variant}", linewidth=1.6, markersize=5)

    ax.set_xlabel("recall@10 (%)")
    ax.set_ylabel(y_label)
    if y_log:
        ax.set_yscale("log")
    ax.set_title(f"{dataset}  |  mode={mode}")
    ax.grid(True, alpha=0.3)
    ax.legend(loc="best", fontsize=9)
    fig.tight_layout()
    os.makedirs(PLOTS_DIR, exist_ok=True)
    out = os.path.join(PLOTS_DIR, fname)
    fig.savefig(out, dpi=140)
    plt.close(fig)
    print(f"  → {out}")


def main():
    rows = load_agg()
    if not rows:
        print("no aggregated.csv — run pareto.py first.")
        return
    # Recall-curve plots: single-threaded only so the DiskANN thread-sweep
    # rows (which reach ~8000 QPS at one canonical recall point) don't
    # dominate and collapse the full recall curve. Thread scaling has its
    # own dedicated plot below.
    single = [r for r in rows if str(r.get("threads", "1")) == "1"]
    datasets = sorted({r["dataset"] for r in single})
    modes    = sorted({r["mode"] for r in single})
    for ds in datasets:
        for m in modes:
            plot_panel(single, ds, m, "mean_ms_median",
                       "mean latency (ms, lower is better)",
                       y_log=True,  fname=f"recall_vs_latency__{ds}__{m}.png")
            plot_panel(single, ds, m, "qps_median",
                       "QPS (higher is better)", minimize_y=False,
                       fname=f"recall_vs_qps__{ds}__{m}.png")
            # App-level bytes/query is meaningful in every mode (cache-agnostic).
            plot_panel(single, ds, m, "bytes_per_query_app_median",
                       "application bytes read per query (lower is better)",
                       y_log=True,  fname=f"recall_vs_bytes__{ds}__{m}.png")
    thread_sweep_plot(rows)


def thread_sweep_plot(agg_rows):
    """Plot QPS vs thread count for rows matching THREAD_SWEEP_PARAMS."""
    from configs.grid import THREAD_SWEEP_PARAMS
    import json as _json
    wanted = {
        v: {_json.dumps(p, sort_keys=True) for p in plist}
        for v, plist in THREAD_SWEEP_PARAMS.items()
    }
    sweep = [r for r in agg_rows
             if r.get("variant") in wanted
             and r.get("params_json") in wanted[r["variant"]]]
    if not sweep or len({int(r["threads"]) for r in sweep if r.get("threads")}) < 2:
        return
    by_mode = defaultdict(list)
    for r in sweep:
        by_mode[(r["dataset"], r["mode"])].append(r)
    for (ds, m), rs in by_mode.items():
        fig, ax = plt.subplots(figsize=(7, 5))
        groups = defaultdict(list)
        for r in rs:
            groups[r["variant"]].append(r)
        for v, pts in sorted(groups.items()):
            pts = sorted(pts, key=lambda r: int(r["threads"]))
            xs = [int(r["threads"]) for r in pts]
            ys = [_f(r["qps_median"]) for r in pts]
            ax.plot(xs, ys, marker=MARKERS.get(v, "x"), label=v, linewidth=1.6)
        ax.set_xlabel("threads")
        ax.set_ylabel("QPS (median across trials)")
        ax.set_title(f"{ds}  |  mode={m}  |  thread scaling @ fixed op. point")
        ax.set_xscale("log", base=2)
        ax.grid(True, alpha=0.3)
        ax.legend(fontsize=9)
        fig.tight_layout()
        out = os.path.join(PLOTS_DIR, f"threads_vs_qps__{ds}__{m}.png")
        fig.savefig(out, dpi=140); plt.close(fig)
        print(f"  → {out}")


if __name__ == "__main__":
    main()
