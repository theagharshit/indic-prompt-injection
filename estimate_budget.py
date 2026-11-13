#!/usr/bin/env python
"""Estimate LLM-call and token budgets per suite and for the proposed experiment design.

No model is called. Per-episode call counts come from replaying AgentDojo ground truths:
  * a user task whose ground truth has u tool calls needs ~u+1 LLM calls if the agent
    issues one tool call per turn (parallel tool calls lower this; retries / detours raise it);
  * under attack, if the agent also follows an injection task with i calls: ~u+i+1.
We report the midpoint of [u+1, u+i+1] for attacked episodes.
Input tokens per call ~= (system prompt + tool schemas + transcript so far) / 4 chars-per-token
(English; Indic-script payloads tokenize 2-5x worse, but they are a small part of the context).

Usage: python estimate_budget.py [--pairs-per-condition 60] [--models 3] [--suites banking slack]
"""

from __future__ import annotations

import argparse
import json
import math

from agentdojo.agent_pipeline.agent_pipeline import load_system_message
from agentdojo.agent_pipeline.ground_truth_pipeline import GroundTruthPipeline
from agentdojo.agent_pipeline.llms.openai_llm import _function_to_openai
from agentdojo.functions_runtime import FunctionsRuntime
from agentdojo.task_suite.load_suites import get_suites
from agentdojo.types import get_text_content_as_str

from ipi_ml.attack import ENGLISH_TEMPLATE
from ipi_ml.constants import BENCHMARK_VERSION, SUITES

CHARS_PER_TOKEN = 4.0


def suite_stats(suite) -> dict:
    sysmsg = load_system_message(None)
    schema_chars = len(json.dumps([_function_to_openai(t) for t in suite.tools]))
    vectors = suite.get_injection_vector_defaults()
    payload = ENGLISH_TEMPLATE.format(user="Emma Johnson", model="AI assistant", goal="x" * 150)
    env_inj = {k: payload for k in vectors}
    u_calls, u_tok = [], []
    for ut in suite.user_tasks.values():
        env = suite.load_and_inject_default_environment(env_inj)
        env = ut.init_environment(env)
        _, _, _, msgs, _ = GroundTruthPipeline(ut).query(ut.PROMPT, FunctionsRuntime(suite.tools), env)
        n = sum(1 for m in msgs if m["role"] == "assistant" and m["tool_calls"])
        u_calls.append(n)
        # input tokens summed over the n+1 calls: each call sees system+schemas+prompt+transcript so far
        base = len(sysmsg) + schema_chars + len(ut.PROMPT)
        running, tot = 0, 0
        for m in msgs:
            if m["role"] == "assistant" and m["tool_calls"]:
                tot += base + running
                running += len(json.dumps([c.model_dump() for c in m["tool_calls"]]))
            elif m["role"] == "tool":
                running += len(get_text_content_as_str(m["content"]))
        tot += base + running  # final answer call
        u_tok.append(tot / CHARS_PER_TOKEN)
    i_calls = []
    for it in suite.injection_tasks.values():
        env = suite.load_and_inject_default_environment({})
        i_calls.append(len(it.ground_truth(env)))
    mu, mi = sum(u_calls) / len(u_calls), sum(i_calls) / len(i_calls)
    return {
        "user_tasks": len(suite.user_tasks),
        "injection_tasks": len(suite.injection_tasks),
        "pairs": len(suite.user_tasks) * len(suite.injection_tasks),
        "tools": len(suite.tools),
        "tool_schema_tokens": round(schema_chars / CHARS_PER_TOKEN),
        "mean_user_gt_calls": round(mu, 2),
        "mean_injection_gt_calls": round(mi, 2),
        "calls_per_benign_episode": round(mu + 1, 2),
        "calls_per_attacked_episode": round(mu + 1 + mi / 2, 2),
        "input_tokens_per_benign_episode": round(sum(u_tok) / len(u_tok)),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--suites", nargs="+", default=SUITES)
    ap.add_argument("--pairs-per-condition", type=int, default=None,
                    help="--limit used per attack condition (default: all pairs)")
    ap.add_argument("--models", type=int, default=3)
    ap.add_argument("--payload-langs", type=int, default=5)
    ap.add_argument("--defenses", type=int, default=3, help="incl. no-defense")
    ap.add_argument("--extra-calls-per-episode", type=float, default=0.0,
                    help="e.g. 1 for tool_filter (one extra filtering call)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    suites = get_suites(BENCHMARK_VERSION)
    stats = {n: suite_stats(suites[n]) for n in args.suites}
    if args.json:
        print(json.dumps(stats, indent=2))
        return
    hdr = ("suite", "UT", "IT", "pairs", "tools", "schema_tok", "calls/benign", "calls/attacked", "in_tok/benign_ep")
    print(" | ".join(hdr))
    for n, s in stats.items():
        print(" | ".join(map(str, (n, s["user_tasks"], s["injection_tasks"], s["pairs"], s["tools"],
                                   s["tool_schema_tokens"], s["calls_per_benign_episode"],
                                   s["calls_per_attacked_episode"], s["input_tokens_per_benign_episode"]))))
    print()
    M, L, D = args.models, args.payload_langs, args.defenses
    print(f"Design: {L} payload langs x {M} models x {D} defenses (task lang = en)  +  benign utility "
          f"({L} task langs x {M} x {D})  +  mismatch ({L - 1} task langs x 2 payloads [en, matched] x {M}, no defense)")
    for n, s in stats.items():
        P = min(args.pairs_per_condition or s["pairs"], s["pairs"])
        ca = s["calls_per_attacked_episode"] + args.extra_calls_per_episode
        cb = s["calls_per_benign_episode"] + args.extra_calls_per_episode
        main_eps = L * M * D * P
        benign_eps = L * M * D * s["user_tasks"]
        mism_eps = (L - 1) * 2 * M * P
        calls = main_eps * ca + benign_eps * cb + mism_eps * ca
        per_model = calls / M
        tb = s["input_tokens_per_benign_episode"]
        ta = tb * s["calls_per_attacked_episode"] / s["calls_per_benign_episode"]
        toks = (main_eps + mism_eps) * ta + benign_eps * tb
        print(f"  {n:9s} P={P:3d}: episodes main={main_eps} benign={benign_eps} mismatch={mism_eps} -> "
              f"~{math.ceil(calls):,} LLM calls total (~{math.ceil(per_model):,} per model, "
              f"~{toks / M / 1e6:.1f}M input tokens per model); one attack condition = ~{math.ceil(P * ca):,} calls")


if __name__ == "__main__":
    main()
