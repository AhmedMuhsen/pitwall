"""Controls for the agent evaluation: a model that behaves perfectly must score 100%, a careless one must score about 0.
If the grader couldn't tell them apart, a live score would mean nothing. Both stand-ins run through the real agent loop and the
real tools on the committed data; only the language model is scripted."""
import json
from pathlib import Path

import pytest

from pitwall.agent import run_agent
from pitwall.agent_eval import grade_case, load_cases, summarise
from pitwall.agent_tools import load_context
from pitwall.llm import Completion, ToolCall

CASES = load_cases(Path(__file__).parent.parent / "evals" / "agent_questions.jsonl")


@pytest.fixture(scope="module")
def ctx():
    return load_context(refits=0)


def say(text):
    return Completion(text=text, tool_calls=[], stop="end_turn", usage={"input_tokens": 400, "output_tokens": 60, "cost_usd": None}, raw=None)


def call(name, args):
    return Completion(text="", tool_calls=[ToolCall("t1", name, dict(args))], stop="tool_use",
                      usage={"input_tokens": 400, "output_tokens": 60, "cost_usd": None}, raw=None)


class Oracle:
    """Does what each case expects: the right tool call, then an answer built only from the tool's own words."""

    def complete(self, model, system, messages, tools, max_tokens, effort=None):
        case = next(c for c in CASES if c["question"] == messages[0]["content"])
        expect = case["expect"]
        if len(messages) == 1:                                           # first turn: call the tool the case expects
            if expect["behavior"] == "answer":
                return call("compare_strategy", expect["args"])
            if expect["behavior"] == "lookup":
                return call(expect["tools"][0], expect.get("args", {}))
            if expect["behavior"] == "ask":
                return say("Which race and which car do you mean?")
            return say(f"I can't do that: {expect['must_mention'][0]}. The simulator doesn't cover it.")
        result = json.loads(messages[-1]["results"][0]["content"])      # second turn: speak only from the tool result
        return say(result.get("verdict", {}).get("summary") or "Here is what the tool returned.")


class Chatterbox:
    """Never calls a tool, invents numbers and claims optimality."""

    def complete(self, **request):
        return say("Pitting on lap 23 is the optimal strategy: 12.3 s faster.")


def score(client, ctx):
    runs = [run_agent(c["question"], ctx, client) for c in CASES]
    graded = [grade_case(c, r, ctx) for c, r in zip(CASES, runs)]
    return graded, summarise(graded, runs, "claude-sonnet-5-5")


def test_a_perfect_agent_scores_every_question(ctx):
    graded, summary = score(Oracle(), ctx)

    failures = [(g["id"], g["problems"]) for g in graded if not g["passed"]]
    assert failures == []
    assert summary["pass_rate"] == 1.0 and summary["cases"] == 40


def test_a_careless_agent_fails_nearly_everything(ctx):
    graded, summary = score(Chatterbox(), ctx)

    assert summary["passed"] <= 2                         # at most a lucky "ask"/"decline" wording
    assert summary["by_check"]["clean_wording"]["passed"] == 0     # every answer claims the optimal strategy
    assert summary["by_check"]["grounded"]["passed"] < summary["cases"]
    assert summary["by_check"]["called_tool"]["passed"] == 0         # it never used a tool
    assert summary["by_check"]["right_arguments"]["passed"] == 0
