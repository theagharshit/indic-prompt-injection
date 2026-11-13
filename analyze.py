#!/usr/bin/env python
"""Aggregate JSONL run logs into per-condition metrics with 95% Wilson CIs.

Metrics (AgentDojo definitions):
  Utility              share of user tasks solved with NO attack     (runs with --attack none)
  Utility-under-attack share of (user, injection) pairs where the user task was still solved
  ASR (targeted)       share of pairs where the injection task's goal was achieved
                       (AgentDojo's `security` flag == True means the attack succeeded)
Supplementary columns:
  *_state_only         same metric restricted to user tasks whose utility check does NOT read
                       the agent's text answer (robust to answer-language effects)
  utility_digitnorm    utility after mapping native-script digits in the answer to ASCII

Only records with status == "ok" count; errors are reported in `n_errors`. If a pair was
recorded more than once in the same condition, the last "ok" record wins.

Usage: python analyze.py [results/ ...] [--out-prefix results/summary]
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

from ipi_ml.stats import wilson_ci

COND_KEYS = ["suite", "provider", "model", "defense", "attack", "payload_lang", "task_lang", "tool_output",
             "reasoning_effort"]
JOIN_KEYS = ["suite", "provider", "model", "defense", "task_lang", "tool_output", "reasoning_effort"]  # attack rows <- benign utility


def load_records(paths: list[Path]) -> tuple[dict, dict]:
    files: list[Path] = []
    for p in paths:
        files += sorted(p.rglob("*.jsonl")) if p.is_dir() else [p]
    latest: dict = {}
    errors: dict = defaultdict(int)
    for f in files:
        with f.open(encoding="utf-8") as fh:
            for ln, line in enumerate(fh, 1):
                if not line.strip():
                    continue
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    print(f"warning: {f}:{ln} unparsable, skipped", file=sys.stderr)
                    continue
                c = r["condition"]
                ckey = tuple(c.get(k) for k in COND_KEYS)
                if r.get("status") != "ok":
                    errors[ckey] += 1
                    continue
                latest[(ckey, r["user_task_id"], r.get("injection_task_id"))] = r
    by_cond: dict = defaultdict(list)
    for (ckey, _, _), r in latest.items():
        by_cond[ckey].append(r)
    return by_cond, errors


def prop(values: list[bool]) -> dict:
    n, k = len(values), sum(bool(v) for v in values)
    lo, hi = wilson_ci(k, n)
    return {"k": k, "n": n, "rate": (k / n) if n else float("nan"), "ci_low": lo, "ci_high": hi}


def fmt(m: dict | None) -> str:
    if not m or not m["n"]:
        return "--"
    return f"{100 * m['rate']:.1f} [{100 * m['ci_low']:.1f}, {100 * m['ci_high']:.1f}] ({m['k']}/{m['n']})"


def compute(by_cond: dict, errors: dict) -> list[dict]:
    rows = []
    for ckey, recs in sorted(by_cond.items(), key=lambda kv: tuple(str(x) for x in kv[0])):
        cond = dict(zip(COND_KEYS, ckey))
        state_only = [r for r in recs if not r.get("utility_check_reads_output")]
        row = {**cond, "n_errors": errors.get(ckey, 0)}
        if cond["attack"] == "none":
            row["utility"] = prop([r["utility"] for r in recs])
            row["utility_state_only"] = prop([r["utility"] for r in state_only])
            row["utility_digitnorm"] = prop([r.get("utility_digit_normalized", r["utility"]) for r in recs])
        else:
            row["utility_under_attack"] = prop([r["utility"] for r in recs])
            row["utility_under_attack_state_only"] = prop([r["utility"] for r in state_only])
            row["asr"] = prop([r["security"] for r in recs])
        rows.append(row)
    return rows


METRICS = ["utility", "utility_state_only", "utility_digitnorm", "utility_under_attack",
           "utility_under_attack_state_only", "asr"]


def write_csv(rows: list[dict], path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(COND_KEYS + ["n_errors", "metric", "k", "n", "rate", "ci_low", "ci_high"])
        for r in rows:
            for m in METRICS:
                if m in r:
                    v = r[m]
                    w.writerow([r.get(k) for k in COND_KEYS] + [r["n_errors"], m, v["k"], v["n"],
                                f"{v['rate']:.4f}", f"{v['ci_low']:.4f}", f"{v['ci_high']:.4f}"])


def write_markdown(rows: list[dict], path: Path) -> str:
    benign = {tuple(r[k] for k in JOIN_KEYS): r for r in rows if r["attack"] == "none"}
    attack = [r for r in rows if r["attack"] != "none"]
    lines = ["# Results summary", "",
             "Cells: percent [95% Wilson CI] (k/n). Utility = benign run (attack none) with the same "
             "suite/model/defense/task language.", "",
             "## Attack conditions", "",
             "| suite | provider | model | defense | task lang | payload lang | Utility | Utility under attack | "
             "ASR | errors |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for r in attack:
        b = benign.get(tuple(r[k] for k in JOIN_KEYS))
        lines.append(f"| {r['suite']} | {r['provider']} | {r['model']} | {r['defense']} | {r['task_lang']} | "
                     f"{r['payload_lang']} | {fmt(b['utility']) if b else '--'} | {fmt(r['utility_under_attack'])} | "
                     f"{fmt(r['asr'])} | {r['n_errors']} |")
    lines += ["", "## Benign utility (no attack)", "",
              "| suite | provider | model | defense | task lang | Utility | Utility (state-only checks) | "
              "Utility (digit-normalized) | errors |", "|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        if r["attack"] == "none":
            lines.append(f"| {r['suite']} | {r['provider']} | {r['model']} | {r['defense']} | {r['task_lang']} | "
                         f"{fmt(r['utility'])} | {fmt(r['utility_state_only'])} | {fmt(r['utility_digitnorm'])} | "
                         f"{r['n_errors']} |")
    text = "\n".join(lines) + "\n"
    path.write_text(text, encoding="utf-8")
    return text


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="*", type=Path, default=[Path("results")])
    ap.add_argument("--out-prefix", type=Path, default=Path("results/summary"))
    a = ap.parse_args(argv)
    by_cond, errors = load_records(a.paths)
    if not by_cond:
        print("no ok records found", file=sys.stderr)
        return 1
    rows = compute(by_cond, errors)
    a.out_prefix.parent.mkdir(parents=True, exist_ok=True)
    write_csv(rows, a.out_prefix.with_suffix(".csv"))
    print(write_markdown(rows, a.out_prefix.with_suffix(".md")))
    print(f"wrote {a.out_prefix.with_suffix('.csv')} and {a.out_prefix.with_suffix('.md')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
