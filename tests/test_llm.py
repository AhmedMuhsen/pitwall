"""The provider clients, with no network: OpenRouter's HTTP is replaced by a script, Anthropic's SDK by a stand-in."""
import io
import json
import urllib.error
from types import SimpleNamespace as NS

import pytest

from pitwall.agent_tools import TOOL_DEFINITIONS
from pitwall.llm import (
    AnthropicClient,
    AuthenticationFailed,
    LLMError,
    OpenRouterClient,
    OutOfCredits,
    ToolCall,
    anthropic_messages,
    openai_messages,
    openai_tools,
    parse_openai_response,
)

CALL = {"id": "call_1", "type": "function", "function": {"name": "compare_strategy", "arguments": '{"race": "Monza 2024", "car": "LEC", "compounds": [], "pit_laps": []}'}}
BODY = {"choices": [{"message": {"role": "assistant", "content": None, "tool_calls": [CALL]}, "finish_reason": "tool_calls"}],
        "usage": {"prompt_tokens": 120, "completion_tokens": 30, "cost": 0.0004}}
TEXT = {"choices": [{"message": {"role": "assistant", "content": "All good."}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 4}}


def response(body):
    class Reply(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *exc): return False
    return Reply(json.dumps(body).encode())


def http_error(code, message="nope", headers=None):
    return urllib.error.HTTPError("https://x", code, "err", headers or {}, io.BytesIO(json.dumps({"error": {"code": code, "message": message}}).encode()))


class Script:
    """An opener that returns or raises the scripted items in order, and records the requests."""

    def __init__(self, *items):
        self.items, self.requests = list(items), []

    def __call__(self, request, timeout=None):
        self.requests.append(request)
        item = self.items.pop(0)
        if isinstance(item, Exception):
            raise item
        return response(item)


def client(*items, attempts=3):
    sleeps = []
    return OpenRouterClient("sk-test", attempts=attempts, opener=Script(*items), sleep=sleeps.append), sleeps


def complete(c):
    return c.complete("anthropic/claude-haiku-5.5", "system rules", [{"role": "user", "content": "hi"}], TOOL_DEFINITIONS, 500, "medium")


def test_tool_definitions_become_openai_function_tools():
    tools = openai_tools(TOOL_DEFINITIONS)

    assert [t["function"]["name"] for t in tools] == ["list_races", "list_cars", "compare_strategy"]
    assert all(t["type"] == "function" and "strict" not in t["function"] and t["function"]["parameters"]["type"] == "object" for t in tools)


def test_the_neutral_conversation_in_openai_form():
    calls = [ToolCall("a", "list_races", {}), ToolCall("b", "list_cars", {"race": "Monza 2024"})]
    messages = [{"role": "user", "content": "q"}, {"role": "assistant", "text": "", "tool_calls": calls, "raw": None},
                {"role": "tool", "results": [{"id": "a", "content": "{}", "is_error": False}, {"id": "b", "content": "[]", "is_error": False}]}]

    out = openai_messages("rules", messages)

    assert [m["role"] for m in out] == ["system", "user", "assistant", "tool", "tool"]
    assert out[2]["content"] is None and out[2]["tool_calls"][1]["function"] == {"name": "list_cars", "arguments": '{"race": "Monza 2024"}'}
    assert out[3] == {"role": "tool", "tool_call_id": "a", "content": "{}"}


def test_parsing_a_tool_call_response_and_a_text_response():
    done = parse_openai_response(BODY)
    assert done.stop == "tool_use" and done.tool_calls == [ToolCall("call_1", "compare_strategy", {"race": "Monza 2024", "car": "LEC", "compounds": [], "pit_laps": []})]
    assert done.usage == {"input_tokens": 120, "output_tokens": 30, "cost_usd": 0.0004}
    text = parse_openai_response(TEXT)
    assert (text.text, text.stop, text.tool_calls, text.usage["cost_usd"]) == ("All good.", "end_turn", [], None)
    for finish, stop in (("length", "max_tokens"), ("content_filter", "refusal"), ("error", "error")):
        assert parse_openai_response({"choices": [{"message": {"content": "x"}, "finish_reason": finish}]}).stop == stop


def test_a_model_that_returns_broken_tool_arguments_does_not_crash():
    broken = {"choices": [{"message": {"tool_calls": [{**CALL, "function": {"name": "compare_strategy", "arguments": "{not json"}}]}, "finish_reason": "tool_calls"}]}

    parsed = parse_openai_response(broken)

    assert parsed.tool_calls[0].input == {"_unparsed_arguments": "{not json"}      # the tool will report bad_input


def test_a_successful_request_sends_the_key_the_model_and_the_tools():
    c, _ = client(BODY)

    reply = complete(c)

    request = c.opener.requests[0]
    assert request.get_header("Authorization") == "Bearer sk-test" and request.full_url.endswith("/chat/completions")
    sent = json.loads(request.data)
    assert sent["model"] == "anthropic/claude-haiku-5.5" and sent["max_tokens"] == 500 and sent["messages"][0] == {"role": "system", "content": "system rules"}
    assert len(sent["tools"]) == 3 and reply.stop == "tool_use"


def test_no_key_is_a_clear_error_not_a_request(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    with pytest.raises(AuthenticationFailed, match="OPENROUTER_API_KEY"):
        complete(OpenRouterClient(opener=Script()))


def test_out_of_credits_and_bad_keys_are_not_retried():
    c, sleeps = client(http_error(402, "Insufficient credits"))
    with pytest.raises(OutOfCredits, match="Insufficient credits"):
        complete(c)
    c, sleeps = client(http_error(401, "Invalid key"))
    with pytest.raises(AuthenticationFailed):
        complete(c)
    c, sleeps = client(http_error(400, "model does not support tools"))
    with pytest.raises(LLMError, match="does not support tools"):
        complete(c)
    assert sleeps == [] and c.opener.items == []


def test_rate_limits_and_server_errors_are_retried_honouring_retry_after():
    c, sleeps = client(http_error(429, headers={"Retry-After": "7"}), http_error(503), TEXT)

    assert complete(c).text == "All good."
    assert sleeps == [7.0, 4.0]                      # Retry-After first, then exponential backoff (2 ** attempt)


def test_an_error_hidden_in_an_http_200_is_noticed_and_retried_if_transient():
    c, sleeps = client({"error": {"code": 502, "message": "provider down"}}, TEXT)
    assert complete(c).text == "All good."
    c, _ = client({"error": {"code": 400, "message": "bad model"}})
    with pytest.raises(LLMError, match="bad model"):
        complete(c)


def test_gives_up_after_the_attempts_with_the_last_problem():
    c, sleeps = client(http_error(503), http_error(503), http_error(503), attempts=3)

    with pytest.raises(LLMError, match="gave up after 3 attempts"):
        complete(c)
    assert len(sleeps) == 2


def test_the_anthropic_client_normalises_its_replies():
    block = NS(type="tool_use", id="t1", name="list_races", input={})
    fake = NS(messages=NS(create=lambda **request: NS(content=[NS(type="text", text="hm"), block], stop_reason="tool_use",
                                                       usage=NS(input_tokens=50, output_tokens=8))))
    reply = AnthropicClient(fake).complete("claude-sonnet-5-5", "rules", [{"role": "user", "content": "q"}], TOOL_DEFINITIONS, 100, "medium")

    assert reply.stop == "tool_use" and reply.text == "hm" and reply.tool_calls == [ToolCall("t1", "list_races", {})]
    assert reply.usage == {"input_tokens": 50, "output_tokens": 8, "cost_usd": None} and reply.raw[1] is block


def test_anthropic_messages_group_results_and_return_thinking_unchanged():
    raw = [NS(type="thinking"), NS(type="tool_use")]
    out = anthropic_messages([{"role": "user", "content": "q"}, {"role": "assistant", "text": "", "tool_calls": [], "raw": raw},
                              {"role": "tool", "results": [{"id": "a", "content": "{}", "is_error": True}, {"id": "b", "content": "[]", "is_error": False}]}])

    assert out[1]["content"] is raw
    assert out[2] == {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "a", "content": "{}", "is_error": True},
                                                  {"type": "tool_result", "tool_use_id": "b", "content": "[]", "is_error": False}]}


def test_reasoning_details_are_echoed_back_when_the_model_sent_them():
    from pitwall.llm import make_client
    raw = {"content": None, "reasoning_details": [{"type": "reasoning.text", "text": "think"}]}
    messages = [{"role": "user", "content": "q"}, {"role": "assistant", "text": "", "tool_calls": [ToolCall("a", "list_races", {})], "raw": raw}]

    assert openai_messages("rules", messages)[2]["reasoning_details"] == raw["reasoning_details"]
    assert "reasoning_details" not in openai_messages("rules", [messages[0], {**messages[1], "raw": "plain"}])[2]
    with pytest.raises(LLMError, match="unknown provider"):
        make_client("nowhere")
