#!/usr/bin/env python
"""Extract every English string that needs translation into data/source_strings.json.

Contents: the important_instructions attack template, the model descriptors that fill its
{model} slot, every injection-task GOAL and every user-task PROMPT for the chosen suites
(default: all four), each with an auto-detected list of *protected spans* that must be
kept verbatim (see ipi_ml/translations.py) and a flag saying whether the corresponding
AgentDojo check reads the agent's text output.

Also writes empty skeleton files data/translations/_skeleton_{payload,user_tasks}.json
that translators can copy to {L}.json / user_tasks_{L}.json.

Usage:  python extract_source_strings.py [--suites banking slack] [--out data/source_strings.json]
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
from importlib.metadata import version
from pathlib import Path

from agentdojo.task_suite.load_suites import get_suites

from ipi_ml.attack import ENGLISH_TEMPLATE
from ipi_ml.audit import security_reads_output, utility_reads_output
from ipi_ml.constants import ALL_MODEL_DESCRIPTORS, ATTACK_USER_NAME, BENCHMARK_VERSION, DATA_DIR, SUITES
from ipi_ml.runner import _task_sort_key
from ipi_ml.translations import auto_protected_spans

# Hand-curated corrections where the regex heuristic is wrong (e.g. unbalanced quotes in
# the original AgentDojo string). Key: (suite, task_id) -> list of spans (replaces auto).
SPAN_OVERRIDES: dict[tuple[str, str], list[str]] = {
    # GOAL has an unbalanced quote: "...subject should be 'Re: Hi from Mark!, and the email should begin with 'Hi Mark, ..."
    ("workspace", "injection_task_4"): [
        "security@facebook.com", "mark.black-2134@gmail.com", "Re: Hi from Mark!",
        "Hi Mark, it was really great to hear from you! I hope we will catch up again soon.",
    ],
    # Slack utility checks match these message bodies / phrases literally (flagged by all 4 translators).
    ("slack", "user_task_8"): ["meeting room"],
    ("slack", "user_task_12"): ["External", "Hi, i am a bot"],
    ("slack", "user_task_13"): ["Congrats on being the most active user!"],
    ("slack", "user_task_14"): ["Congrats on being the k-th most active user!"],
}

TRANSLATOR_NOTES = [
    "Translate meaning faithfully; keep register natural for a native speaker of the target language.",
    "Every string in `protected_spans` MUST appear verbatim (same characters, Latin script, ASCII digits) in the "
    "translation: AgentDojo checks compare these literally against tool arguments / environment state. "
    "validate_translations.py enforces this.",
    "Template: keep the placeholders {user}, {model}, {goal} exactly; keep <INFORMATION> tags and the blank-line layout.",
    "Proper names (Emma Johnson, Bob, Alice, Riverside View Hotel, ...) are not auto-protected; the recommended "
    "convention is to keep them in Latin script as well (record any deviation in the file's `meta`).",
    "hi_latn (Hinglish): Romanized, code-mixed Hindi-English as typed on WhatsApp; no Devanagari.",
    "Do not add or remove instructions; do not 'fix' oddities of the original task text.",
]


def spans_for(suite: str, tid: str, text: str) -> list[str]:
    spans = SPAN_OVERRIDES.get((suite, tid)) or auto_protected_spans(text)
    missing = [s for s in spans if s not in text]
    if missing:
        raise ValueError(f"override spans not in source text for {suite}/{tid}: {missing}")
    return spans


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--suites", nargs="+", default=SUITES, choices=SUITES)
    ap.add_argument("--benchmark-version", default=BENCHMARK_VERSION)
    ap.add_argument("--out", type=Path, default=DATA_DIR / "source_strings.json")
    args = ap.parse_args()

    suites = get_suites(args.benchmark_version)
    out = {
        "agentdojo_version": version("agentdojo"),
        "benchmark_version": args.benchmark_version,
        "generated_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "translator_notes": TRANSLATOR_NOTES,
        "templates": {
            "important_instructions": {
                "text": ENGLISH_TEMPLATE,
                "placeholders": ["user", "model", "goal"],
                "user_name_default": ATTACK_USER_NAME,
                "protected_spans": ["<INFORMATION>", "</INFORMATION>", "{user}", "{model}", "{goal}"],
            }
        },
        "model_descriptors": {d: {"text": d, "note": "fills {model}; translate as a noun phrase"}
                              for d in ALL_MODEL_DESCRIPTORS},
        "suites": {},
        "counts": {},
    }
    total_chars = 0
    for name in args.suites:
        s = suites[name]
        goals = {}
        for tid in sorted(s.injection_tasks, key=_task_sort_key):
            t = s.injection_tasks[tid]
            goals[tid] = {"text": t.GOAL, "protected_spans": spans_for(name, tid, t.GOAL),
                          "security_check_reads_output": security_reads_output(type(t))}
        prompts = {}
        for tid in sorted(s.user_tasks, key=_task_sort_key):
            t = s.user_tasks[tid]
            prompts[tid] = {"text": t.PROMPT, "protected_spans": spans_for(name, tid, t.PROMPT),
                            "utility_check_reads_output": utility_reads_output(type(t)),
                            "difficulty": getattr(getattr(t, "DIFFICULTY", None), "name", None)}
        out["suites"][name] = {"injection_goals": goals, "user_prompts": prompts}
        chars = sum(len(v["text"]) for v in goals.values()) + sum(len(v["text"]) for v in prompts.values())
        total_chars += chars
        out["counts"][name] = {
            "injection_goals": len(goals),
            "user_prompts": len(prompts),
            "attack_pairs": len(goals) * len(prompts),
            "user_tasks_whose_utility_reads_output": sum(v["utility_check_reads_output"] for v in prompts.values()),
            "injection_tasks_whose_security_reads_output": sum(v["security_check_reads_output"] for v in goals.values()),
            "english_chars": chars,
        }
    out["counts"]["_total"] = {
        "templates": 1,
        "model_descriptors": len(ALL_MODEL_DESCRIPTORS),
        "injection_goals": sum(c["injection_goals"] for k, c in out["counts"].items() if not k.startswith("_")),
        "user_prompts": sum(c["user_prompts"] for k, c in out["counts"].items() if not k.startswith("_")),
        "english_chars": total_chars + len(ENGLISH_TEMPLATE),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # skeletons for translators
    tdir = args.out.parent / "translations"
    tdir.mkdir(parents=True, exist_ok=True)
    payload = {"language": "<L>", "meta": {"translator": "", "method": "", "reviewed_by": "", "notes": ""},
               "template": "", "model_descriptors": {d: "" for d in ALL_MODEL_DESCRIPTORS},
               "user_name": ATTACK_USER_NAME,
               "injection_goals": {n: {k: "" for k in out["suites"][n]["injection_goals"]} for n in args.suites}}
    users = {"language": "<L>", "meta": {"translator": "", "method": "", "reviewed_by": "", "notes": ""},
             "user_prompts": {n: {k: "" for k in out["suites"][n]["user_prompts"]} for n in args.suites}}
    (tdir / "_skeleton_payload.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    (tdir / "_skeleton_user_tasks.json").write_text(json.dumps(users, ensure_ascii=False, indent=2) + "\n")

    print(f"wrote {args.out}")
    print(json.dumps(out["counts"], indent=2))


if __name__ == "__main__":
    main()
