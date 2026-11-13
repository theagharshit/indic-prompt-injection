"""Deterministic offline stand-in for an LLM (no network). Used by the dry-run test.

Behaviour per episode:
  1. replays the user task's ground-truth tool calls one per turn;
  2. if behaviour == "comply" and any tool output it has *seen* contains one of the exact
     injection strings the runner registered for this episode (compared after removing
     whitespace/quotes, because the YAML formatter folds and re-quotes long strings) -- i.e.
     the translated payload really reached the model's context in readable form -- it then
     replays the injection task's ground truth;
  3. answers with the user task's GROUND_TRUTH_OUTPUT.
It records every tool output it saw in `self.seen_tool_outputs` for test assertions.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Sequence

from agentdojo.agent_pipeline.base_pipeline_element import BasePipelineElement
from agentdojo.functions_runtime import EmptyEnv, Env, FunctionCall, FunctionsRuntime
from agentdojo.types import ChatAssistantMessage, ChatMessage, get_text_content_as_str, text_content_block_from_string


def _canon(s: str) -> str:
    """Remove whitespace/quotes/backslashes: YAML folds long strings and re-quotes them."""
    return re.sub(r"[\s'\"\\]", "", s)


class _PassThroughToolFilter(BasePipelineElement):
    def __init__(self, llm: "MockLLM"):
        self.llm = llm

    def query(self, query, runtime, env=EmptyEnv(), messages=[], extra_args={}):
        self.llm.events.append({"type": "llm_call", "usage": None, "tool_choice": "none"})
        return query, runtime, env, messages, extra_args


class MockLLM(BasePipelineElement):
    def __init__(self, behaviour: str = "comply", name: str = "mock:mock"):
        assert behaviour in ("comply", "ignore")
        self.behaviour = behaviour
        self.name = name
        self.events: list[dict] = []
        self.seen_tool_outputs: list[str] = []
        self.set_episode(None, None, {})

    def make_tool_filter(self) -> BasePipelineElement:
        return _PassThroughToolFilter(self)

    def reset_events(self) -> None:
        self.events = []

    def set_episode(self, user_task, injection_task, injections: dict[str, str]) -> None:
        self.user_task = user_task
        self.injection_task = injection_task
        self.injection_texts = [v for v in injections.values() if v]
        self._plan: list[FunctionCall] | None = None
        self._injected = False
        self.triggered = False

    def query(
        self,
        query: str,
        runtime: FunctionsRuntime,
        env: Env = EmptyEnv(),
        messages: Sequence[ChatMessage] = [],
        extra_args: dict = {},
    ) -> tuple[str, FunctionsRuntime, Env, Sequence[ChatMessage], dict]:
        self.events.append({"type": "llm_call", "usage": None, "tool_choice": "auto"})
        tool_texts = [get_text_content_as_str(m["content"]) for m in messages if m["role"] == "tool" and m["content"]]
        self.seen_tool_outputs = tool_texts
        if self._plan is None:
            self._plan = list(self.user_task.ground_truth(env)) if self.user_task is not None else []
        if not self._plan and self.behaviour == "comply" and not self._injected and self.injection_task is not None:
            seen = _canon("".join(tool_texts))
            if any(_canon(inj) in seen for inj in self.injection_texts):
                self.triggered = True
                self._injected = True
                self._plan = list(self.injection_task.ground_truth(env))
        if self._plan:
            call = self._plan.pop(0)
            call = FunctionCall(function=call.function, args=dict(call.args), id=f"call_{uuid.uuid4().hex[:8]}")
            out = ChatAssistantMessage(role="assistant", content=[text_content_block_from_string("")], tool_calls=[call])
        else:
            answer = getattr(self.user_task, "GROUND_TRUTH_OUTPUT", "") or "Done."
            out = ChatAssistantMessage(role="assistant", content=[text_content_block_from_string(answer)], tool_calls=None)
        return query, runtime, env, [*messages, out], extra_args
