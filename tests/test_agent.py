"""The agent loop, run against a scripted stand-in for the model (no network, no API key)."""
import json
from types import SimpleNamespace as NS

import pytest

from pitwall.agent import SYSTEM_PROMPT, run_agent
from pitwall.agent_tools import TOOL_DEFINITIONS


def text(t):
    return NS(type="text", text=t)


def tool_use(id, name, **input):
    return NS(type="tool_use", id=id, name=name, input=input)


def reply(content, stop, tokens=(10, 5)):
    return NS(content=content, stop_reason=stop, usage=NS(input_tokens=tokens[0], output_tokens=tokens[1]))


class ScriptedClient:
    """Returns the scripted replies in order and records every request."""

    def __init__(self, replies):
        self.replies, self.requests = list(replies), []
        self.messages = NS(create=self._create)

    def _create(self, **request):
        self.requests.append({**request, "messages": list(request["messages"])})
        return self.replies.pop(0)


def fake_tool(ctx, name, tool_input):
    return {"echo": name, **tool_input}


def test_a_tool_call_then_an_answer():
    client = ScriptedClient([reply([tool_use("t1", "list_cars", race="Monza 2024")], "tool_use"),
                             reply([text("LEC is available.")], "end_turn", tokens=(20, 7))])

    result = run_agent("Who can I pick at Monza 2024?", {}, client, tool_runner=fake_tool)

    assert result["answer"] == "LEC is available."
    assert result["tool_calls"] == [{"name": "list_cars", "input": {"race": "Monza 2024"},
                                     "result": {"echo": "list_cars", "race": "Monza 2024"}}]
    assert (result["stop_reason"], result["turns"], result["usage"]) == ("end_turn", 2, {"input_tokens": 30, "output_tokens": 12})
    # The second request carries the assistant turn and the tool result for that exact tool_use id.
    follow_up = client.requests[1]["messages"]
    assert [m["role"] for m in follow_up] == ["user", "assistant", "user"]
    block = follow_up[2]["content"][0]
    assert block["type"] == "tool_result" and block["tool_use_id"] == "t1" and block["is_error"] is False
    assert json.loads(block["content"]) == {"echo": "list_cars", "race": "Monza 2024"}


def test_every_request_has_the_rules_the_tools_and_no_forced_tool_choice():
    client = ScriptedClient([reply([text("Which race?")], "end_turn")])

    run_agent("What if he had pitted earlier?", {}, client, model="claude-sonnet-5-5", effort="medium", tool_runner=fake_tool)

    request = client.requests[0]
    assert request["system"] == SYSTEM_PROMPT and request["tools"] == TOOL_DEFINITIONS
    assert request["model"] == "claude-sonnet-5-5" and request["output_config"] == {"effort": "medium"}
    assert "tool_choice" not in request          # forced tool use is rejected by these models
    assert "temperature" not in request


def test_parallel_tool_calls_are_answered_in_one_user_message():
    client = ScriptedClient([reply([tool_use("a", "list_races"), tool_use("b", "list_cars", race="Monza 2024")], "tool_use"),
                             reply([text("done")], "end_turn")])

    run_agent("q", {}, client, tool_runner=fake_tool)

    results = client.requests[1]["messages"][-1]["content"]
    assert [r["tool_use_id"] for r in results] == ["a", "b"]


def test_only_malformed_calls_are_marked_as_errors():
    def runner(ctx, name, tool_input):
        return {"error": {"list_races": "unknown_tool", "list_cars": "race_excluded"}[name], "message": "x"}
    client = ScriptedClient([reply([tool_use("a", "list_races"), tool_use("b", "list_cars", race="Monaco 2024")], "tool_use"),
                             reply([text("ok")], "end_turn")])

    run_agent("q", {}, client, tool_runner=runner)

    flags = {r["tool_use_id"]: r["is_error"] for r in client.requests[1]["messages"][-1]["content"]}
    assert flags == {"a": True, "b": False}      # "race excluded" is an answer, not a failure of the tool


def test_thinking_blocks_are_passed_back_unchanged():
    thinking = NS(type="thinking", thinking="", signature="sig")
    client = ScriptedClient([reply([thinking, tool_use("a", "list_races")], "tool_use"), reply([thinking, text("hi")], "end_turn")])

    result = run_agent("q", {}, client, tool_runner=fake_tool)

    assert client.requests[1]["messages"][1]["content"][0] is thinking
    assert result["answer"] == "hi"


def test_stopping_conditions():
    looping = ScriptedClient([reply([tool_use(f"t{i}", "list_races")], "tool_use") for i in range(3)])
    stopped = run_agent("q", {}, looping, max_turns=3, tool_runner=fake_tool)
    assert (stopped["answer"], stopped["stop_reason"], stopped["turns"]) == ("", "max_turns", 3)

    refused = run_agent("q", {}, ScriptedClient([reply([text("I can't")], "refusal")]), tool_runner=fake_tool)
    assert (refused["answer"], refused["stop_reason"]) == ("", "refusal")

    cut = run_agent("q", {}, ScriptedClient([reply([text("partial")], "max_tokens")]), tool_runner=fake_tool)
    assert (cut["answer"], cut["stop_reason"]) == ("partial", "max_tokens")

    paused = ScriptedClient([reply([text("working")], "pause_turn"), reply([text("final")], "end_turn")])
    assert run_agent("q", {}, paused, tool_runner=fake_tool)["answer"] == "final"


def test_effort_can_be_left_at_the_model_default():
    client = ScriptedClient([reply([text("ok")], "end_turn")])

    run_agent("q", {}, client, effort=None, tool_runner=fake_tool)

    assert "output_config" not in client.requests[0]
