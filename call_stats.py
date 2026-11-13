#!/usr/bin/env python
"""Per-model call statistics from run logs: latency, retries by HTTP status (429/5xx),
calls and tokens per episode, wall-clock per episode. Uses only logged events.

Usage: python call_stats.py results/pilot2 [more paths ...]
"""

from __future__ import annotations

import argparse
import json
import statistics as st
from collections import defaultdict
from pathlib import Path


def pct(xs, q):
    if not xs:
        return float("nan")
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(q * (len(xs) - 1))))]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="+", type=Path)
    a = ap.parse_args(argv)
    files = [f for p in a.paths for f in (sorted(p.rglob("*.jsonl")) if p.is_dir() else [p])]
    agg = defaultdict(lambda: {"lat": [], "retry": defaultdict(int), "eps": 0, "ok": 0, "err": 0, "calls": [],
                               "tok": [], "dur": [], "retry_sleep": 0.0})
    for f in files:
        for line in f.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            c = r["condition"]
            key = f"{c['model']} (effort={c.get('reasoning_effort')})"
            g = agg[key]
            g["eps"] += 1
            g["ok" if r["status"] == "ok" else "err"] += 1
            calls = [e for e in r["events"] if e["type"] == "llm_call"]
            g["lat"] += [e["latency_s"] for e in calls if e.get("latency_s") is not None]
            g["calls"].append(len(calls))
            g["tok"] += [e["usage"]["total_tokens"] for e in calls if e.get("usage")]
            for e in r["events"]:
                if e["type"] in ("retry", "retry_exhausted", "daily_quota", "bad_request"):
                    g["retry"][f"{e['type']}:{e.get('status')}"] += 1
                    g["retry_sleep"] += e.get("sleep_s") or 0
            if r["status"] == "ok" and r.get("duration_s"):
                g["dur"].append(r["duration_s"])
    print("| model | episodes ok/err | calls | latency s (median / mean / p90 / max) | retries & errors by status | "
          "calls/episode | tokens/call (mean) | wall-clock s/episode (mean) |")
    print("|---|---|---|---|---|---|---|---|")
    for k, g in sorted(agg.items()):
        lat = g["lat"]
        print(f"| {k} | {g['ok']}/{g['err']} | {len(lat)} | "
              f"{st.median(lat):.1f} / {st.mean(lat):.1f} / {pct(lat, .9):.1f} / {max(lat):.1f} | "
              f"{dict(g['retry']) or '-'} | {st.mean(g['calls']):.1f} | "
              f"{(st.mean(g['tok']) if g['tok'] else float('nan')):.0f} | "
              f"{(st.mean(g['dur']) if g['dur'] else float('nan')):.0f} |" if lat else f"| {k} | no calls |")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
