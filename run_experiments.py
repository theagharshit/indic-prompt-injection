#!/usr/bin/env python
"""Run one experimental condition (provider x model x suite x payload-lang x task-lang x defense).

Every episode is appended as one JSON line (raw transcript, injections, prompt, per-pair
utility/security booleans, call/usage events, provenance). Re-running the same command
skips pairs already recorded with status "ok" (resumable); errored pairs are retried.

Examples
  # attack condition, Hindi payload, English user prompt, 60 seeded pairs
  python run_experiments.py --provider groq --model llama-3.3-70b-versatile --suite banking \
      --payload-lang hi --task-lang en --defense none --limit 60 --sleep 2.5
  # benign utility in Telugu (no attack)
  python run_experiments.py --provider gemini --model gemini-2.0-flash --suite banking \
      --attack none --task-lang te
  # offline smoke test
  python run_experiments.py --provider mock --model mock --suite banking --payload-lang en --limit 3
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import traceback
from importlib.metadata import version
from pathlib import Path

from agentdojo.agent_pipeline.agent_pipeline import load_system_message
from agentdojo.task_suite.load_suites import get_suite

from ipi_ml.attack import make_attack
from ipi_ml.constants import (
    ATTACK_NAME,
    BENCHMARK_VERSION,
    CODE_DIR,
    DATA_DIR,
    DEFENSES,
    LANGUAGES,
    SUITES,
    TRANSLATIONS_DIR,
)
from ipi_ml.providers import PROVIDERS, ProviderError, QuotaExhaustedError, build_pipeline, make_llm
from ipi_ml.runner import (
    AGENTDOJO_VERSION,
    append_record,
    condition_id,
    enumerate_pairs,
    harness_revision,
    load_done,
    make_record,
    pair_key,
    run_episode,
    sample_pairs,
)
from ipi_ml.translations import (
    MissingTranslationError,
    TranslationValidationError,
    UserPromptTranslations,
    _check_text,
    load_source_strings,
)


def _slug(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", s).strip("-")


def _err_body(e: Exception) -> str:
    body = getattr(e, "body", None)
    try:
        return json.dumps(body, ensure_ascii=False)[:1500]
    except (TypeError, ValueError):
        return repr(body)[:1500]


def default_out(a) -> Path:
    payload = a.payload_lang if a.attack != "none" else "none"
    return (Path("results") / a.suite / f"{a.provider}__{_slug(a.model)}" / a.defense / a.attack /
            f"task-{a.task_lang}__payload-{payload}.jsonl")


def parse_args(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--provider", required=True, choices=sorted(PROVIDERS))
    ap.add_argument("--model", required=True, help="provider model id, e.g. gemini-2.0-flash, llama-3.3-70b-versatile")
    ap.add_argument("--suite", required=True, choices=SUITES)
    ap.add_argument("--payload-lang", default="en", choices=sorted(LANGUAGES), help="language of injected payload")
    ap.add_argument("--task-lang", default="en", choices=sorted(LANGUAGES), help="language of the user prompt")
    ap.add_argument("--defense", default="none", choices=DEFENSES)
    ap.add_argument("--attack", default=ATTACK_NAME, choices=[ATTACK_NAME, "none"],
                    help="'none' = benign utility run over user tasks only")
    ap.add_argument("--limit", type=int, default=None, help="seeded subsample of N (user,injection) pairs")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--user-tasks", nargs="*", default=None)
    ap.add_argument("--injection-tasks", nargs="*", default=None)
    ap.add_argument("--out", type=Path, default=None, help="JSONL output (default: results/<suite>/<prov__model>/...)")
    ap.add_argument("--sleep", type=float, default=0.0, help="minimum seconds between LLM calls")
    ap.add_argument("--max-retries", type=int, default=10, help="retries on 429/5xx before stopping (resume later)")
    ap.add_argument("--backoff-base", type=float, default=2.0)
    ap.add_argument("--backoff-max", type=float, default=120.0)
    ap.add_argument("--max-calls", type=int, default=None, help="stop cleanly after ~N LLM calls in this invocation")
    ap.add_argument("--tool-output", default="unicode", choices=["unicode", "stock"],
                    help="tool-output YAML: 'unicode' keeps native scripts (default); 'stock' = AgentDojo default, "
                         "which escapes non-ASCII as \\uXXXX")
    ap.add_argument("--reasoning-effort", default=None, choices=["none", "minimal", "low", "medium", "high"],
                    help="OpenAI-compatible `reasoning_effort` (Gemini maps it to its thinking level). "
                         "Default: not sent (provider default). Part of the condition id.")
    ap.add_argument("--timeout", type=float, default=180.0, help="per-request timeout (s)")
    ap.add_argument("--temperature", type=float, default=0.0)
    ap.add_argument("--max-tokens", type=int, default=None)
    ap.add_argument("--translations-dir", type=Path, default=TRANSLATIONS_DIR)
    ap.add_argument("--source-strings", type=Path, default=DATA_DIR / "source_strings.json")
    ap.add_argument("--benchmark-version", default=BENCHMARK_VERSION)
    ap.add_argument("--max-consecutive-errors", type=int, default=5,
                    help="abort if this many pairs in a row fail with a (non-quota) error")
    ap.add_argument("--no-retry-errors", action="store_true", help="also skip pairs previously recorded as error")
    ap.add_argument("--skip-provider-errors", action="store_true",
                    help="if a pair still fails after all retries (server errors), record it as an excluded error "
                         "pair and continue instead of stopping the run")
    ap.add_argument("--mock-behaviour", default="comply", choices=["comply", "ignore"])
    ap.add_argument("--plan", action="store_true", help="print the pairs that would run and exit (no LLM calls)")
    return ap.parse_args(argv)


def preflight_translations(a, suite, pairs, attack_obj) -> tuple[dict, UserPromptTranslations]:
    """Fail BEFORE any API call if anything needed for this run is missing or violates the
    protected-span rules. Returns {inj_id: goal} and the prompt translator."""
    source = load_source_strings(a.source_strings) if a.source_strings.exists() else None
    errors: list[str] = []
    goals = {}
    if attack_obj is not None:
        for inj_id in sorted({i for _, i in pairs}):
            it = suite.get_injection_task_by_id(inj_id)
            try:
                goals[inj_id] = attack_obj.translated_goal(it)
            except MissingTranslationError as e:
                errors.append(str(e))
                continue
            if source is not None and a.payload_lang != "en":
                spans = source["suites"][suite.name]["injection_goals"][inj_id]["protected_spans"]
                _check_text(a.payload_lang, f"{suite.name}/{inj_id}", it.GOAL, goals[inj_id], spans, errors)
    upt = UserPromptTranslations(a.task_lang, a.translations_dir)
    for ut_id in sorted({u for u, _ in pairs}):
        ut = suite.get_user_task_by_id(ut_id)
        try:
            p = upt.prompt(suite.name, ut_id, ut.PROMPT)
        except MissingTranslationError as e:
            errors.append(str(e))
            continue
        if source is not None and a.task_lang != "en":
            spans = source["suites"][suite.name]["user_prompts"][ut_id]["protected_spans"]
            _check_text(a.task_lang, f"{suite.name}/{ut_id}", ut.PROMPT, p, spans, errors)
    if source is None and (a.payload_lang != "en" or a.task_lang != "en"):
        print(f"WARNING: {a.source_strings} missing -> protected-span check skipped", file=sys.stderr)
    if errors:
        raise TranslationValidationError("Translation preflight failed:\n  " + "\n  ".join(errors))
    return goals, upt


def main(argv=None) -> int:
    a = parse_args(argv)
    if a.attack == "none" and a.payload_lang != "en":
        print("note: --payload-lang ignored for --attack none", file=sys.stderr)
    suite = get_suite(a.benchmark_version, a.suite)
    llm = make_llm(a.provider, a.model, sleep_s=a.sleep, max_retries=a.max_retries, base_delay_s=a.backoff_base,
                   max_delay_s=a.backoff_max, temperature=a.temperature, max_tokens=a.max_tokens,
                   mock_behaviour=a.mock_behaviour, reasoning_effort=a.reasoning_effort, timeout_s=a.timeout)
    system_message = load_system_message(None)
    pipeline = build_pipeline(llm, a.defense, system_message, tool_output=a.tool_output)

    attack_obj = None
    if a.attack != "none":
        attack_obj = make_attack(a.payload_lang, suite, pipeline, a.translations_dir)

    all_pairs = enumerate_pairs(suite, attack=attack_obj is not None, user_tasks=a.user_tasks,
                                injection_tasks=a.injection_tasks)
    pairs = sample_pairs(all_pairs, a.limit, a.seed)
    _, upt = preflight_translations(a, suite, pairs, attack_obj)

    cond = {
        "suite": a.suite, "benchmark_version": a.benchmark_version, "provider": a.provider, "model": a.model,
        "defense": a.defense, "attack": a.attack, "payload_lang": a.payload_lang if attack_obj else None,
        "task_lang": a.task_lang, "temperature": a.temperature, "tool_output": a.tool_output,
        "reasoning_effort": a.reasoning_effort,
    }
    cid = condition_id(cond)
    cond_full = {
        **cond, "seed": a.seed, "limit": a.limit, "n_pairs_total": len(all_pairs), "pipeline_name": pipeline.name,
        "agentdojo_version": AGENTDOJO_VERSION, "openai_version": version("openai"),
        "system_message_sha256": hashlib.sha256(system_message.encode()).hexdigest()[:16],
        "user_prompt_translation_sha256": upt.sha256,
        "attack_provenance": attack_obj.provenance() if attack_obj else None,
        "harness_revision": harness_revision(CODE_DIR),
        "sleep_s": a.sleep, "max_tokens": a.max_tokens,
        "llm_settings": llm.settings() if hasattr(llm, "settings") else None,
    }
    out = a.out or default_out(a)
    done = load_done(out, cid, retry_errors=not a.no_retry_errors)
    todo = [p for p in pairs if pair_key(*p) not in done]
    print(f"[{cid}] {pipeline.name} suite={a.suite} attack={a.attack} payload={cond['payload_lang']} "
          f"task={a.task_lang} defense={a.defense}: {len(pairs)} pairs selected ({len(all_pairs)} total), "
          f"{len(pairs) - len(todo)} done, {len(todo)} to run -> {out}")
    if a.plan:
        for p in todo:
            print("  ", pair_key(*p))
        return 0

    calls_used = 0
    n_ok = n_err = consecutive_err = 0
    for ut_id, it_id in todo:
        if a.max_calls is not None and calls_used >= a.max_calls:
            print(f"--max-calls {a.max_calls} reached; stopping (resume by re-running).")
            break
        user_task = suite.get_user_task_by_id(ut_id)
        inj_task = suite.get_injection_task_by_id(it_id) if it_id else None
        injections = attack_obj.attack(user_task, inj_task) if inj_task is not None else {}
        prompt = upt.prompt(suite.name, ut_id, user_task.PROMPT)
        if hasattr(llm, "reset_events"):
            llm.reset_events()
        if hasattr(llm, "set_episode"):
            llm.set_episode(user_task, inj_task, injections)
        try:
            res = run_episode(suite, pipeline, user_task, inj_task, injections, prompt)
            extra = {"mock_triggered": llm.triggered} if hasattr(llm, "triggered") else None
            rec = make_record(cond_full, cid, user_task, inj_task, prompt, injections, res, llm.events, "ok",
                              extra=extra)
            n_ok += 1
        except QuotaExhaustedError as e:
            print(f"STOP: {e}", file=sys.stderr)
            return 3
        except ProviderError as e:
            if not a.skip_provider_errors:
                print(f"STOP: {e}", file=sys.stderr)
                return 2
            # record as an excluded error pair (never scored), then move on
            rec = make_record(cond_full, cid, user_task, inj_task, prompt, injections, None, llm.events, "error",
                              error=f"ProviderError (skipped after retries): {e}")
            n_err += 1
            consecutive_err += 1
        except KeyboardInterrupt:
            print("interrupted; completed pairs are saved.", file=sys.stderr)
            return 130
        except Exception as e:  # model/API error for this pair: record, continue
            rec = make_record(cond_full, cid, user_task, inj_task, prompt, injections, None, llm.events, "error",
                              error=f"{type(e).__name__}: {e} body={_err_body(e)}\n{traceback.format_exc()[-1500:]}")
            n_err += 1
            consecutive_err += 1
        else:
            consecutive_err = 0
        calls_used += rec["llm_calls"]
        append_record(out, rec)
        flag = "" if rec["status"] == "ok" else " ERROR"
        print(f"  {pair_key(ut_id, it_id):40s} utility={rec.get('utility')} security={rec.get('security')} "
              f"calls={rec['llm_calls']}{flag}", flush=True)
        if consecutive_err >= a.max_consecutive_errors:
            print(f"STOP: {consecutive_err} consecutive errors; last: {rec['error'][:300]}", file=sys.stderr)
            return 4
    print(json.dumps({"ok": n_ok, "errors": n_err, "llm_calls": calls_used, "out": str(out)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
