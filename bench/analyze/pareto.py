"""
Reduce bench/results/runs.csv to a Pareto frontier per (algo, variant, mode).

Dimensions considered: (recall10, mean_ms, bytes_read_per_query).
For each group we:
  1. Average across trials (median + IQR on key metrics).
  2. Keep points that aren't dominated on (higher recall, lower latency,
     lower bytes_read) simultaneously.
  3. Write bench/results/pareto_summary.csv with the frontier.

Also writes a closest-recall interpolation per fixed target {90, 95, 99} so
the headline table stops cherry-picking.
"""

import csv
import json
import os
import statistics
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from configs.grid import RUNS_CSV, RESULTS_DIR, ACTIVE_MODES


AGG_COLS = ("recall10", "mean_ms", "qps",
            "bytes_read_per_query", "ios_per_query", "p99_ms")


def _to_float(x):
    try: return float(x) if x not in (None, "",) else None
    except ValueError: return None


def load_runs(path=RUNS_CSV):
    rows = []
    if not os.path.exists(path):
        return rows
    with open(path) as f:
        for r in csv.DictReader(f):
            rows.append(r)
    return rows


def group_key(r):
    return (r["algo"], r["variant"], r["dataset"], r["mode"],
            r.get("ram_cap_bytes", ""), r["params_json"], r.get("threads", "1"))


def aggregate(rows):
    """Per-group: median + IQR over the AGG_COLS."""
    buckets = defaultdict(list)
    for r in rows:
        buckets[group_key(r)].append(r)
    out = []
    for key, group in buckets.items():
        agg = {
            "algo": key[0], "variant": key[1], "dataset": key[2],
            "mode": key[3], "ram_cap_bytes": key[4],
            "params_json": key[5], "threads": key[6],
            "n_trials": len(group),
        }
        for col in AGG_COLS:
            vals = [_to_float(r.get(col)) for r in group]
            vals = [v for v in vals if v is not None]
            if not vals:
                agg[f"{col}_median"] = ""
                agg[f"{col}_iqr"] = ""
                continue
            vals.sort()
            agg[f"{col}_median"] = round(statistics.median(vals), 4)
            if len(vals) >= 4:
                q1, q3 = vals[len(vals)//4], vals[(3*len(vals))//4]
                agg[f"{col}_iqr"] = round(q3 - q1, 4)
            else:
                agg[f"{col}_iqr"] = round(max(vals) - min(vals), 4)
        out.append(agg)
    return out


def pareto_frontier(points, maximize=("recall10_median",),
                    minimize=("mean_ms_median", "bytes_read_per_query_median")):
    """Return subset of points not dominated. A point p dominates q iff
    p is >= on all maximize cols and <= on all minimize cols, with
    strict improvement in at least one."""
    def dominates(p, q):
        better = False
        for c in maximize:
            pv, qv = _to_float(p[c]), _to_float(q[c])
            if pv is None or qv is None: return False
            if pv < qv: return False
            if pv > qv: better = True
        for c in minimize:
            pv, qv = _to_float(p[c]), _to_float(q[c])
            if pv is None or qv is None: return False
            if pv > qv: return False
            if pv < qv: better = True
        return better

    front = []
    for p in points:
        if any(dominates(q, p) for q in points if q is not p):
            continue
        front.append(p)
    return front


def frontier_per_group(aggregated):
    by_group = defaultdict(list)
    for a in aggregated:
        g = (a["algo"], a["variant"], a["dataset"], a["mode"],
             a["ram_cap_bytes"], a["threads"])
        by_group[g].append(a)
    out = []
    for g, pts in by_group.items():
        front = pareto_frontier(pts)
        for p in front:
            out.append({**p, "pareto_group": "|".join(map(str, g))})
    return out


def closest_recall_table(aggregated, targets=(85.0, 90.0, 95.0)):
    """For each (algo, variant, mode, ram_cap) group, pick the single
    operating point whose recall is closest to each target."""
    by_group = defaultdict(list)
    for a in aggregated:
        g = (a["algo"], a["variant"], a["dataset"], a["mode"],
             a["ram_cap_bytes"], a["threads"])
        by_group[g].append(a)
    rows = []
    for g, pts in by_group.items():
        for t in targets:
            best, best_d = None, float("inf")
            for p in pts:
                r = _to_float(p["recall10_median"])
                if r is None: continue
                d = abs(r - t)
                if d < best_d:
                    best, best_d = p, d
            if best:
                rows.append({
                    "algo": g[0], "variant": g[1], "dataset": g[2],
                    "mode": g[3], "ram_cap_bytes": g[4], "threads": g[5],
                    "target_recall": t,
                    "achieved_recall": best["recall10_median"],
                    "params_json": best["params_json"],
                    "mean_ms": best["mean_ms_median"],
                    "qps": best["qps_median"],
                    "bytes_read_per_query": best["bytes_read_per_query_median"],
                    "ios_per_query": best["ios_per_query_median"],
                    "distance_to_target": round(best_d, 3),
                })
    return rows


def _write_csv(rows, path, cols=None):
    if not rows:
        print(f"  (no rows for {path})"); return
    cols = cols or list(rows[0].keys())
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in cols})
    print(f"  → {path}  ({len(rows)} rows)")


def main():
    rows = load_runs()
    print(f"loaded {len(rows)} runs from {RUNS_CSV}")
    if not rows:
        return
    rows = [r for r in rows if r.get("mode") in ACTIVE_MODES]
    print(f"  kept {len(rows)} rows after filtering to ACTIVE_MODES={ACTIVE_MODES}")
    agg     = aggregate(rows)
    front   = frontier_per_group(agg)
    targets = closest_recall_table(agg)

    os.makedirs(RESULTS_DIR, exist_ok=True)
    _write_csv(agg,     os.path.join(RESULTS_DIR, "aggregated.csv"))
    _write_csv(front,   os.path.join(RESULTS_DIR, "pareto_summary.csv"))
    _write_csv(targets, os.path.join(RESULTS_DIR, "closest_recall.csv"))


if __name__ == "__main__":
    main()
