"""Mocked tests for the OpenAI-compatible provider layer (no network)."""

from __future__ import annotations

import httpx
import openai
import pytest
from openai.types.chat import ChatCompletion

from agentdojo.functions_runtime import FunctionsRuntime, make_function
from agentdojo.types import ChatSystemMessage, ChatUserMessage, text_content_block_from_string

from ipi_ml.providers import (
    QuotaExhaustedError, ProviderError,
    RateLimitedOpenAILLM,
    RetryPolicy,
    _retry_after_seconds,
    build_pipeline,
)


def get_balance(account: str) -> str:
    """Get the balance of an account.

    :param account: the account id
    """
    return f"balance of {account}: 100.0"


RUNTIME_FUNCS = [make_function(get_balance)]


def _completion(content=None, tool_calls=None) -> ChatCompletion:
    msg = {"role": "assistant", "content": content}
    if tool_calls:
        msg["tool_calls"] = tool_calls
    return ChatCompletion.model_validate({
        "id": "x", "object": "chat.completion", "created": 0, "model": "m",
        "choices": [{"index": 0, "finish_reason": "tool_calls" if tool_calls else "stop", "message": msg}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12},
    })


def _tc(i, sig=None, cid="call_1"):
    d = {"id": cid, "type": "function", "function": {"name": "get_balance", "arguments": f'{{"account": "A{i}"}}'}}
    if sig:
        d["extra_content"] = {"google": {"thought_signature": sig}}
    return d


def _status_error(cls, status, body=None, headers=None):
    resp = httpx.Response(status, headers=headers or {}, request=httpx.Request("POST", "https://x"))
    return cls(f"Error code: {status}", response=resp, body=body)


class ScriptedClient:
    """Fake openai client: returns/raises a scripted sequence and records request kwargs."""

    def __init__(self, script):
        self.script = list(script)
        self.requests = []
        self.chat = type("Chat", (), {"completions": self})()

    def create(self, **kw):
        self.requests.append(kw)
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class GeminiLikeClient(ScriptedClient):
    """Emulates Gemini 3.x: rejects an assistant tool_call without its thought signature."""

    def create(self, **kw):
        for m in kw["messages"]:
            for tc in m.get("tool_calls") or []:
                if not (tc.get("extra_content") or {}).get("google", {}).get("thought_signature"):
                    self.requests.append(kw)
                    raise _status_error(openai.BadRequestError, 400, [{"error": {
                        "code": 400, "status": "INVALID_ARGUMENT",
                        "message": "Function call is missing a thought_signature in functionCall parts."}}])
        return super().create(**kw)


def _llm(client, **kw):
    sleeps = []
    llm = RateLimitedOpenAILLM(client, "gemini-x", "gemini", RetryPolicy(max_retries=kw.pop("max_retries", 5),
                                                                         sleep_fn=sleeps.append), **kw)
    llm.reset_events()
    return llm, sleeps


def _msgs():
    return [ChatSystemMessage(role="system", content=[text_content_block_from_string("sys")]),
            ChatUserMessage(role="user", content=[text_content_block_from_string("balance of A1 and A2?")])]


def _run_agent(llm):
    pipe = build_pipeline(llm, "none", "sys")
    rt = FunctionsRuntime(RUNTIME_FUNCS)
    from agentdojo.functions_runtime import EmptyEnv

    _, _, _, messages, _ = pipe.query("balance of A1 and A2?", rt, EmptyEnv())
    return messages


def test_thought_signature_round_trip_multi_turn():
    client = GeminiLikeClient([
        _completion(tool_calls=[_tc(1, sig="SIG-ONE", cid="call_1")]),
        _completion(tool_calls=[_tc(2, sig="SIG-TWO", cid="call_1")]),  # provider reuses an id
        _completion(content="A1 and A2 both have 100.0"),
    ])
    llm, _ = _llm(client)
    messages = _run_agent(llm)
    assert messages[-1]["content"][0]["content"] == "A1 and A2 both have 100.0"
    # 3rd request carries both earlier tool calls, each with ITS OWN signature, and unique ids
    last = client.requests[-1]["messages"]
    tcs = [tc for m in last if m.get("tool_calls") for tc in m["tool_calls"]]
    assert [tc["extra_content"]["google"]["thought_signature"] for tc in tcs] == ["SIG-ONE", "SIG-TWO"]
    assert len({tc["id"] for tc in tcs}) == 2
    tool_msgs = [m for m in last if m["role"] == "tool"]
    assert [m["tool_call_id"] for m in tool_msgs] == [tc["id"] for tc in tcs]
    # agentdojo semantics intact: FunctionCall objects carry only function/args/id
    calls = [c for m in messages if m["role"] == "assistant" and m["tool_calls"] for c in m["tool_calls"]]
    assert [c.args for c in calls] == [{"account": "A1"}, {"account": "A2"}]
    assert [e.get("thought_signatures") for e in llm.events if e["type"] == "llm_call"] == [1, 1, None]


def test_without_signature_support_gemini_like_server_rejects():
    """Sanity check of the emulator: dropping the signature reproduces the pilot's 400."""
    client = GeminiLikeClient([_completion(tool_calls=[_tc(1, sig="S")]), _completion(content="x")])
    llm, _ = _llm(client)
    orig = llm._to_assistant_message

    def drop(message):
        out = orig(message)
        llm._call_extras.clear()
        return out

    llm._to_assistant_message = drop
    with pytest.raises(openai.BadRequestError):
        _run_agent(llm)
    assert any(e["type"] == "bad_request" and "thought_signature" in e["body"] for e in llm.events)


def test_signatures_reset_per_episode():
    client = ScriptedClient([_completion(tool_calls=[_tc(1, sig="S")]), _completion(content="ok")])
    llm, _ = _llm(client)
    _run_agent(llm)
    assert llm._call_extras
    llm.reset_events()
    assert llm._call_extras == {} and llm.events == []


def test_no_extra_content_for_providers_without_it():
    client = ScriptedClient([_completion(tool_calls=[_tc(1)]), _completion(content="ok")])
    llm, _ = _llm(client)
    _run_agent(llm)
    tcs = [tc for m in client.requests[-1]["messages"] if m.get("tool_calls") for tc in m["tool_calls"]]
    assert tcs and all("extra_content" not in tc for tc in tcs)


@pytest.mark.parametrize("status,cls", [(500, openai.InternalServerError), (503, openai.InternalServerError),
                                        (429, openai.RateLimitError)])
def test_transient_errors_retried_not_recorded_as_behaviour(status, cls):
    client = ScriptedClient([_status_error(cls, status), _status_error(cls, status), _completion(content="ok")])
    llm, sleeps = _llm(client)
    _run_agent(llm)
    kinds = [(e["type"], e.get("status")) for e in llm.events]
    assert kinds == [("retry", status), ("retry", status), ("llm_call", None)]
    assert len(sleeps) == 2 and sleeps[1] > sleeps[0] * 1.5


def test_persistent_5xx_stops_run_instead_of_recording():
    client = ScriptedClient([_status_error(openai.InternalServerError, 503)] * 4)
    llm, _ = _llm(client, max_retries=3)
    # persistent 5xx: ProviderError (stops the run by default; --skip-provider-errors records it as excluded)
    with pytest.raises(ProviderError):
        _run_agent(llm)
    assert llm.events[-1]["type"] == "retry_exhausted"


def test_connection_and_timeout_errors_retried():
    req = httpx.Request("POST", "https://x")
    client = ScriptedClient([openai.APIConnectionError(request=req), openai.APITimeoutError(request=req),
                             _completion(content="ok")])
    llm, sleeps = _llm(client)
    _run_agent(llm)
    assert [e["type"] for e in llm.events] == ["retry", "retry", "llm_call"]


def test_daily_quota_stops_immediately():
    body = [{"error": {"code": 429, "status": "RESOURCE_EXHAUSTED", "details": [
        {"@type": "type.googleapis.com/google.rpc.QuotaFailure",
         "violations": [{"quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier", "quotaValue": "250"}]}]}}]
    client = ScriptedClient([_status_error(openai.RateLimitError, 429, body)])
    llm, sleeps = _llm(client)
    with pytest.raises(QuotaExhaustedError, match="daily quota"):
        _run_agent(llm)
    assert sleeps == [] and len(client.requests) == 1


def test_retry_delay_parsed_from_gemini_body():
    body = [{"error": {"code": 429, "details": [{"@type": "type.googleapis.com/google.rpc.RetryInfo",
                                                 "retryDelay": "37s"}]}}]
    assert _retry_after_seconds(_status_error(openai.RateLimitError, 429, body)) == 37.0
    assert _retry_after_seconds(_status_error(openai.RateLimitError, 429, None, {"retry-after": "5"})) == 5.0
    client = ScriptedClient([_status_error(openai.RateLimitError, 429, body), _completion(content="ok")])
    llm, sleeps = _llm(client)
    _run_agent(llm)
    assert sleeps[0] >= 37.0


def test_reasoning_effort_sent_and_recorded():
    client = ScriptedClient([_completion(content="ok")])
    llm, _ = _llm(client, reasoning_effort="low")
    _run_agent(llm)
    assert client.requests[0]["reasoning_effort"] == "low"
    assert llm.settings()["reasoning_effort"] == "low"
    client2 = ScriptedClient([_completion(content="ok")])
    llm2, _ = _llm(client2)
    _run_agent(llm2)
    assert "reasoning_effort" not in client2.requests[0]


def test_inline_gemma_thoughts_stripped_and_logged():
    client = ScriptedClient([
        _completion(content="<thought>check balances first</thought>", tool_calls=[_tc(1)]),
        _completion(content="<thought>both are 100</thought>Both balances are 100.0"),
    ])
    llm, _ = _llm(client)
    messages = _run_agent(llm)
    assert messages[-1]["content"][0]["content"] == "Both balances are 100.0"
    assert all("<thought>" not in str(m["content"]) for m in messages if m["role"] == "assistant")
    thoughts = [e["text"] for e in llm.events if e["type"] == "inline_thought"]
    assert thoughts == ["check balances first", "both are 100"]
    # history sent back to the model has no thoughts either
    assert "<thought>" not in str(client.requests[-1]["messages"])


def test_bad_request_body_logged():
    body = [{"error": {"code": 400, "message": "Request contains an invalid argument."}}]
    client = ScriptedClient([_status_error(openai.BadRequestError, 400, body)])
    llm, _ = _llm(client)
    with pytest.raises(openai.BadRequestError):
        _run_agent(llm)
    assert "invalid argument" in llm.events[-1]["body"]
