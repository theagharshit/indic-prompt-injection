"""Static audit: which AgentDojo checks read the model's *text output*.

Translating the user prompt can make the agent answer in that language. AgentDojo
utility checks that only inspect environment state / tool-call traces are unaffected;
checks that do substring matching on `model_output` (names, numbers, addresses) can
fail if the agent transliterates names or writes native-script digits. We flag those
tasks so analyses can report them separately.

Method: parse the source of the task's own `utility` / `utility_from_traces`
(`security` / `security_from_traces` for injection tasks) -- skipping the abstract
base-class defaults -- and check whether the *body* (docstring excluded) references
the `model_output` parameter.
"""

from __future__ import annotations

import ast
import inspect
import textwrap
from functools import lru_cache

from agentdojo.base_tasks import BaseInjectionTask, BaseUserTask

_BASES = (BaseUserTask, BaseInjectionTask, object)


def _method_reads_output(fn) -> bool:
    try:
        src = textwrap.dedent(inspect.getsource(fn))
    except (OSError, TypeError):
        return False
    tree = ast.parse(src)
    func = tree.body[0]
    assert isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef))
    body = func.body
    if body and isinstance(body[0], ast.Expr) and isinstance(getattr(body[0], "value", None), ast.Constant):
        body = body[1:]  # drop docstring
    for stmt in body:
        for node in ast.walk(stmt):
            if isinstance(node, ast.Name) and node.id == "model_output":
                return True
    return False


def _reads_output(cls, method_names: tuple[str, ...]) -> bool:
    for m in method_names:
        owner = next((k for k in cls.__mro__ if m in k.__dict__), None)
        if owner is None or owner in _BASES:
            continue  # inherited default (returns None / abstract)
        if _method_reads_output(owner.__dict__[m]):
            return True
    return False


@lru_cache
def utility_reads_output(user_task_cls) -> bool:
    return _reads_output(user_task_cls, ("utility", "utility_from_traces"))


@lru_cache
def security_reads_output(injection_task_cls) -> bool:
    return _reads_output(injection_task_cls, ("security", "security_from_traces"))
