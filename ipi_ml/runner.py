"""Episode execution, pair sampling, JSONL logging and resume logic."""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import random
import subprocess
import time
import warnings
from collections.abc import Sequence
from importlib.metadata import version as _pkg_version
from pathlib import Path

from agentdojo.agent_pipeline.base_pipeline_element import BasePipelineElement
from agentdojo.agent_pipeline.errors import AbortAgentError
from agentdojo.base_tasks import BaseInjectionTask, BaseUserTask
from agentdojo.functions_runtime import FunctionsRuntime
from agentdojo.logging import Logger
from agentdojo.task_suite.task_suite import (
    TaskSuite,
    functions_stack_trace_from_messages,
    model_output_from_messages,
)
from agentdojo.types import get_text_content_as_str, text_content_block_from_string

from ipi_ml.audit import security_reads_output, utility_reads_output

SCHEMA_VERSION = 1
AGENTDOJO_VERSION = _pkg_version("agentdojo")


class CapturingLogger(Logger):
    """AgentDojo pipelines call Logger.get().log(messages) after every element; keep the last."""

    def __init__(self) -> None:
        self.messages: list = []
        self.errors: list[str] = []

    def log(self, messages, **kwargs) -> None:
        self.messages = list(messages)

    def log_error(self, error: str) -> None:
        self.errors.append(str(error))


_NATIVE_DIGITS = {}
for _base in (0x0966, 0x09E6, 0x0C66):  # Devanagari, Bengali, Telugu digit zero
    for _i in range(10):
        _NATIVE_DIGITS[chr(_base + _i)] = str(_i)
_DIGIT_TABLE = str.maketrans(_NATIVE_DIGITS)


def normalize_digits(text: str) -> str:
    return text.translate(_DIGIT_TABLE)


def run_episode(
    suite: TaskSuite,
    pipeline: BasePipelineElement,
    user_task: BaseUserTask,
    injection_task: BaseInjectionTask | None,
    injections: dict[str, str],
    prompt: str,
) -> dict:
    """Mirror of agentdojo 0.1.35 `TaskSuite.run_task_with_pipeline`, except that the
    prompt sent to the agent can differ from `user_task.PROMPT` (task-language setting)
    and the full transcript is returned. Utility/security are computed by AgentDojo's own
    checks (`suite._check_task_result`) on the original task objects."""
    environment = suite.load_and_inject_default_environment(injections)
    task_environment = user_task.init_environment(environment)
    pre_environment = task_environment.model_copy(deep=True)
    runtime = FunctionsRuntime(suite.tools)
    model_output = None
    messages: list = []
    aborted = None
    attempts = 0
    t0 = time.time()
    with CapturingLogger() as cap:
        for _ in range(3):  # AgentDojo retries up to 3x when the final output is None
            attempts += 1
            try:
                _, _, task_environment, messages, _ = pipeline.query(prompt, runtime, task_environment)
            except AbortAgentError as e:
                task_environment, messages, aborted = e.task_environment, e.messages, str(e)
            model_output = model_output_from_messages(messages)
            if model_output is not None:
                break
    if model_output is None:
        warnings.warn(f"Model output was None for task {user_task.ID}")
    trace = functions_stack_trace_from_messages(messages)
    utility = suite._check_task_result(user_task, model_output or [], pre_environment, task_environment, trace)
    security = None
    if injection_task is not None:
        security = suite._check_task_result(injection_task, model_output or [], pre_environment, task_environment, trace)

    # Supplementary: utility after mapping native-script digits in the final answer to ASCII.
    out_text = get_text_content_as_str(model_output or [])
    norm = normalize_digits(out_text)
    if norm != out_text:
        utility_norm = suite._check_task_result(
            user_task, [text_content_block_from_string(norm)], pre_environment, task_environment, trace
        )
    else:
        utility_norm = utility
    return {
        "utility": bool(utility),
        "security": None if security is None else bool(security),
        "utility_digit_normalized": bool(utility_norm),
        "final_output": out_text,
        "messages": messages,
        "tool_calls": [{"function": c.function, "args": c.args} for c in trace],
        "aborted_by_defense": aborted,
        "pipeline_attempts": attempts,
        "logger_errors": cap.errors,
        "duration_s": round(time.time() - t0, 3),
    }


# ------------------------------------------------------------------------------------------
# Pair enumeration / sampling
# ------------------------------------------------------------------------------------------
def _task_sort_key(task_id: str):
    head, _, num = task_id.rpartition("_")
    return (head, int(num)) if num.isdigit() else (task_id, 0)


def enumerate_pairs(suite: TaskSuite, attack: bool, user_tasks: Sequence[str] | None = None,
                    injection_tasks: Sequence[str] | None = None) -> list[tuple[str, str | None]]:
    uts = sorted(user_tasks or suite.user_tasks.keys(), key=_task_sort_key)
    if not attack:
        return [(u, None) for u in uts]
    its = sorted(injection_tasks or suite.injection_tasks.keys(), key=_task_sort_key)
    return [(u, i) for u in uts for i in its]


def sample_pairs(pairs: list, limit: int | None, seed: int) -> list:
    """Seeded subsample that depends only on (pair list, limit, seed) -- NOT on language,
    model or defense -- so every condition evaluates the same pairs."""
    if not limit or limit >= len(pairs):
        return list(pairs)
    rng = random.Random(seed)
    chosen = rng.sample(range(len(pairs)), limit)
    return [pairs[k] for k in sorted(chosen)]


# ------------------------------------------------------------------------------------------
# JSONL output
# ------------------------------------------------------------------------------------------
def _json_default(o):
    if hasattr(o, "model_dump"):
        return o.model_dump(mode="json")
    if isinstance(o, (set, tuple)):
        return list(o)
    return repr(o)


def pair_key(user_task_id: str, injection_task_id: str | None) -> str:
    return f"{user_task_id}|{injection_task_id or 'none'}"


def condition_id(cond: dict) -> str:
    keys = ["suite", "benchmark_version", "provider", "model", "defense", "attack", "payload_lang", "task_lang",
            "temperature", "tool_output", "reasoning_effort"]
    return hashlib.sha256(json.dumps({k: cond.get(k) for k in keys}, sort_keys=True).encode()).hexdigest()[:16]


def load_done(out_path: Path, cond_id: str, retry_errors: bool = True) -> set[str]:
    done: set[str] = set()
    if not out_path.exists():
        return done
    with out_path.open(encoding="utf-8") as f:
        for ln, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                warnings.warn(f"{out_path}:{ln}: unparsable line (truncated write?) -- ignored")
                continue
            if rec.get("condition_id") != cond_id:
                raise RuntimeError(
                    f"{out_path} contains records of a different condition ({rec.get('condition_id')} != {cond_id}). "
                    "Use a different --out file per condition."
                )
            if rec.get("status") == "ok" or not retry_errors:
                done.add(pair_key(rec["user_task_id"], rec.get("injection_task_id")))
    return done


def append_record(out_path: Path, record: dict) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False, default=_json_default)
    with out_path.open("a", encoding="utf-8") as f:
        f.write(line + "\n")
        f.flush()


def harness_revision(code_dir: Path) -> str:
    """sha256 over the harness source files (ipi_ml/*.py + run_experiments.py), plus the git
    commit if the code dir is a git checkout. Logged with every record for provenance."""
    h = hashlib.sha256()
    for f in sorted([*(code_dir / "ipi_ml").glob("*.py"), code_dir / "run_experiments.py"]):
        h.update(f.name.encode())
        h.update(f.read_bytes())
    rev = f"src-sha256:{h.hexdigest()[:16]}"
    try:
        git = subprocess.run(["git", "-C", str(code_dir), "rev-parse", "HEAD"], capture_output=True, text=True,
                             timeout=5).stdout.strip()
        if git:
            rev += f" git:{git[:12]}"
    except Exception:
        pass
    return rev


def make_record(cond: dict, cond_id: str, user_task: BaseUserTask, injection_task: BaseInjectionTask | None,
                prompt: str, injections: dict, result: dict | None, events: list, status: str,
                error: str | None = None, extra: dict | None = None) -> dict:
    rec = {
        "schema_version": SCHEMA_VERSION,
        "timestamp_utc": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "condition_id": cond_id,
        "condition": cond,
        "user_task_id": user_task.ID,
        "injection_task_id": injection_task.ID if injection_task is not None else None,
        "status": status,
        "error": error,
        "prompt": prompt,
        "prompt_is_original_english": prompt == user_task.PROMPT,
        "injections": injections,
        "utility_check_reads_output": utility_reads_output(type(user_task)),
        "security_check_reads_output": (security_reads_output(type(injection_task))
                                        if injection_task is not None else None),
        "llm_calls": sum(1 for e in events if e.get("type") == "llm_call"),
        "events": events,
    }
    if result is not None:
        rec.update(result)
    if extra:
        rec.update(extra)
    return rec
