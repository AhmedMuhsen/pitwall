"""The agent loop, run against a scripted stand-in for the model (no network, no API key)."""
import json

from pitwall.agent import SYSTEM_PROMPT, run_agent
from pitwall.agent_tools import TOOL_DEFINITIONS
from pitwall.llm import Completion, ToolCall


def reply(text="", calls=(), stop="end_turn", tokens=(10, 5), cost=None, raw="raw"):
    return Completion(text=text, tool_calls=list(calls), stop=stop, usage={"input_tokens": tokens[0], "output_tokens": tokens[1], "cost_usd": cost}, raw=raw)


class ScriptedClient:
    """Returns the scripted replies in order and records every request."""

    def __init__(self, replies):
        self.replies, self.requests = list(replies), []

    def complete(self, **request):
        self.requests.append({**request, "messages": list(request["messages"])})
        return self.replies.pop(0)


def fake_tool(ctx, name, tool_input):
    return {"echo": name, **tool_input}


def test_a_tool_call_then_an_answer():
    client = ScriptedClient([reply(calls=[ToolCall("t1", "list_cars", {"race": "Monza 2024"})], stop="tool_use"),
                             reply("LEC is available.", tokens=(20, 7))])

    result = run_agent("Who can I pick at Monza 2024?", {}, client, tool_runner=fake_tool)

    assert result["answer"] == "LEC is available."
    assert result["tool_calls"] == [{"name": "list_cars", "input": {"race": "Monza 2024"},
                                     "result": {"echo": "list_cars", "race": "Monza 2024"}}]
    assert (result["stop_reason"], result["turns"]) == ("end_turn", 2)
    assert result["usage"] == {"input_tokens": 30, "output_tokens": 12, "cost_usd": None}
    follow_up = client.requests[1]["messages"]
    assert [m["role"] for m in follow_up] == ["user", "assistant", "tool"]
    assert follow_up[1]["tool_calls"][0].id == "t1" and follow_up[1]["raw"] == "raw"
    assert follow_up[2]["results"][0]["id"] == "t1" and follow_up[2]["results"][0]["is_error"] is False
    assert json.loads(follow_up[2]["results"][0]["content"]) == {"echo": "list_cars", "race": "Monza 2024"}


def test_every_request_has_the_rules_the_tools_and_the_settings():
    client = ScriptedClient([reply("Which race?")])

    run_agent("What if he had pitted earlier?", {}, client, model="some/model", effort="medium", max_tokens=1234, tool_runner=fake_tool)

    request = client.requests[0]
    assert request["system"] == SYSTEM_PROMPT and request["tools"] == TOOL_DEFINITIONS
    assert (request["model"], request["effort"], request["max_tokens"]) == ("some/model", "medium", 1234)


def test_parallel_tool_calls_are_answered_together():
    client = ScriptedClient([reply(calls=[ToolCall("a", "list_races", {}), ToolCall("b", "list_cars", {"race": "Monza 2024"})], stop="tool_use"),
                             reply("done")])

    run_agent("q", {}, client, tool_runner=fake_tool)

    assert [r["id"] for r in client.requests[1]["messages"][-1]["results"]] == ["a", "b"]


def test_only_malformed_calls_are_marked_as_errors():
    def runner(ctx, name, tool_input):
        return {"error": {"list_races": "unknown_tool", "list_cars": "race_excluded"}[name], "message": "x"}
    client = ScriptedClient([reply(calls=[ToolCall("a", "list_races", {}), ToolCall("b", "list_cars", {"race": "Monaco 2024"})], stop="tool_use"),
                             reply("ok")])

    run_agent("q", {}, client, tool_runner=runner)

    flags = {r["id"]: r["is_error"] for r in client.requests[1]["messages"][-1]["results"]}
    assert flags == {"a": True, "b": False}      # "race excluded" is an answer, not a failure of the tool


def test_stopping_conditions():
    looping = ScriptedClient([reply(calls=[ToolCall(f"t{i}", "list_races", {})], stop="tool_use") for i in range(3)])
    stopped = run_agent("q", {}, looping, max_turns=3, tool_runner=fake_tool)
    assert (stopped["answer"], stopped["stop_reason"], stopped["turns"]) == ("", "max_turns", 3)

    for stop in ("refusal", "error"):
        failed = run_agent("q", {}, ScriptedClient([reply("partial text", stop=stop)]), tool_runner=fake_tool)
        assert (failed["answer"], failed["stop_reason"]) == ("", stop)

    cut = run_agent("q", {}, ScriptedClient([reply("partial", stop="max_tokens")]), tool_runner=fake_tool)
    assert (cut["answer"], cut["stop_reason"]) == ("partial", "max_tokens")

    paused = ScriptedClient([reply("working", stop="pause_turn"), reply("final")])
    assert run_agent("q", {}, paused, tool_runner=fake_tool)["answer"] == "final"


def test_cost_is_summed_when_the_provider_reports_it():
    client = ScriptedClient([reply(calls=[ToolCall("a", "list_races", {})], stop="tool_use", cost=0.0004), reply("ok", cost=0.0006)])

    assert run_agent("q", {}, client, tool_runner=fake_tool)["usage"]["cost_usd"] == 0.001
