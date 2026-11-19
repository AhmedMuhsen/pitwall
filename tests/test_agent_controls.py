"""Controls for the agent evaluation: a model that behaves perfectly must score 100%, a careless one must score about 0.
If the grader couldn't tell them apart, a live score would mean nothing. Both stand-ins run through the real agent loop and the
real tools on the committed data; only the language model is scripted."""
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from pitwall.agent import run_agent
from pitwall.agent_eval import grade_case, load_cases, summarise
from pitwall.agent_tools import load_context

CASES = load_cases(Path(__file__).parent.parent / "evals" / "agent_questions.jsonl")


@pytest.fixture(scope="module")
def ctx():
    return load_context(refits=0)


def reply(content, stop):
    return NS(content=content, stop_reason=stop, usage=NS(input_tokens=400, output_tokens=60))


class Oracle:
    """Does what each case expects: the right tool call, then an answer built only from the tool's own words."""

    def __init__(self):
        self.messages = NS(create=self.create)

    def create(self, **request):
        messages = request["messages"]
        case = next(c for c in CASES if c["question"] == messages[0]["content"])
        expect = case["expect"]
        if len(messages) == 1:                                           # first turn: call the tool the case expects
            if expect["behavior"] == "answer":
                args = expect["args"]
                return reply([NS(type="tool_use", id="t1", name="compare_strategy", input=dict(args))], "tool_use")
            if expect["behavior"] == "lookup":
                args = expect.get("args", {})
                return reply([NS(type="tool_use", id="t1", name=expect["tools"][0], input=dict(args))], "tool_use")
            if expect["behavior"] == "ask":
                return reply([NS(type="text", text="Which race and which car do you mean?")], "end_turn")
            cue = expect["must_mention"][0]
            return reply([NS(type="text", text=f"I can't do that: {cue}. The simulator doesn't cover it.")], "end_turn")
        import json
        result = json.loads(messages[-1]["content"][0]["content"])      # second turn: speak only from the tool result
        text = result.get("verdict", {}).get("summary") or "Here is what the tool returned."
        return reply([NS(type="text", text=text)], "end_turn")


class Chatterbox:
    """Never calls a tool, invents numbers and claims optimality."""

    def __init__(self):
        self.messages = NS(create=lambda **request: reply([NS(type="text", text="Pitting on lap 23 is the optimal strategy: 12.3 s faster.")], "end_turn"))


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
