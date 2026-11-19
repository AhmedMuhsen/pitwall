import collections
from pathlib import Path

import pytest

from pitwall.agent_eval import (
    forbidden_phrases,
    grade_case,
    load_cases,
    numbers_in,
    summarise,
    ungrounded_numbers,
)
from pitwall.agent_tools import _distance, load_context, resolve_car, resolve_race
from pitwall.comparison import custom_strategy

CASES = Path(__file__).parent.parent / "evals" / "agent_questions.jsonl"


@pytest.fixture(scope="module")
def ctx():
    return load_context(refits=0)


def run(answer="ok", calls=(), stop="end_turn", tokens=(100, 20)):
    return {"answer": answer, "tool_calls": list(calls), "stop_reason": stop, "turns": 2,
            "usage": {"input_tokens": tokens[0], "output_tokens": tokens[1]}}


def call(name, result=None, **tool_input):
    return {"name": name, "input": tool_input, "result": result if result is not None else {"ok": True}}


def test_numbers_in():
    assert numbers_in("8.3 s faster; 1:14:41.1 total; 20 of 20; 80%") == ["8.3", "1:14:41.1", "20", "20", "80"]


def test_ungrounded_numbers_hand_examples():
    results = [{"gap_s": -8.3, "real_time": "1:14:41.1", "faster_in_refits": "18 of 20", "interval": "plus or minus 17.2 s"}]

    assert ungrounded_numbers("It is 8.3 s faster, about 8 s, within 17 s, in 18 of 20 refits.", "", results) == []
    assert ungrounded_numbers("The race took 1:14:41.", "", results) == []                       # clock without the decimal
    assert ungrounded_numbers("It is 9.1 s faster and 33 s overall.", "", results) == ["9.1", "33"]
    assert ungrounded_numbers("He pitted on lap 20.", "What if he pitted on lap 20?", []) == []   # numbers from the question
    assert ungrounded_numbers("Two stops in 2024 across 3 stints.", "", []) == []                 # small counts and years are ignored
    assert ungrounded_numbers("About 12 s.", "", [{"x": 8.3}]) == ["12"]


def test_forbidden_phrases_only_when_asserted():
    assert forbidden_phrases("This is the optimal strategy.") == ["optimal"]
    assert forbidden_phrases("It is guaranteed to work. Definitely faster.") == ["guarantee", "definitely"]
    assert forbidden_phrases("I can't say which strategy is optimal.") == []
    assert forbidden_phrases("The model does not claim an optimal strategy, and nothing is guaranteed... not a guarantee.") == []
    assert forbidden_phrases("The model prefers a later stop.") == []


def test_grading_an_answer_case(ctx):
    case = {"id": "c", "group": "named", "question": "What if LEC pitted on lap 20 at Monza 2024?",
            "expect": {"behavior": "answer", "tool": "compare_strategy",
                       "args": {"race": "Monza 2024", "car": "16", "compounds": ["MEDIUM", "HARD"], "pit_laps": [20]}}}
    good = call("compare_strategy", {"gap_s": -5.1}, race="Italian GP 2024", car="Leclerc", compounds=["medium", "hard"], pit_laps=[20])

    assert grade_case(case, run("About 5.1 s faster.", [good]), ctx)["passed"]
    wrong_lap = call("compare_strategy", {"gap_s": -5.1}, race="Monza 2024", car="LEC", compounds=["MEDIUM", "HARD"], pit_laps=[21])
    graded = grade_case(case, run("About 5.1 s faster.", [wrong_lap]), ctx)
    assert not graded["passed"] and graded["checks"]["right_arguments"] is False and graded["checks"]["called_tool"] is True
    wrong_car = call("compare_strategy", {"gap_s": 1.0}, race="Monza 2024", car="NOR", compounds=["MEDIUM", "HARD"], pit_laps=[20])
    assert not grade_case(case, run("1.0 s.", [wrong_car]), ctx)["checks"]["right_arguments"]
    assert not grade_case(case, run("It is faster by 7.7 s.", [good]), ctx)["checks"]["grounded"]
    assert not grade_case(case, run("I don't know."), ctx)["checks"]["called_tool"]
    failed_tool = call("compare_strategy", {"error": "x"}, race="Monza 2024", car="LEC", compounds=["MEDIUM", "HARD"], pit_laps=[20])
    assert not grade_case(case, run("Sorry.", [failed_tool]), ctx)["checks"]["tool_succeeded"]
    assert not grade_case(case, run("", [good], stop="max_tokens"), ctx)["checks"]["finished"]


def test_grading_a_standard_comparison_means_empty_lists(ctx):
    case = {"id": "c", "group": "open", "question": "Was LEC's strategy good at Monza 2024?",
            "expect": {"behavior": "answer", "tool": "compare_strategy", "args": {"race": "Monza 2024", "car": "16", "compounds": [], "pit_laps": []}}}

    assert grade_case(case, run("ok", [call("compare_strategy", race="Monza 2024", car="LEC", compounds=[], pit_laps=[])]), ctx)["passed"]
    invented = call("compare_strategy", race="Monza 2024", car="LEC", compounds=["MEDIUM", "HARD"], pit_laps=[20])
    assert not grade_case(case, run("ok", [invented]), ctx)["checks"]["right_arguments"]


def test_grading_decline_ask_and_lookup(ctx):
    decline = {"id": "d", "group": "decline", "question": "Who is the best driver?",
               "expect": {"behavior": "decline", "must_mention": ["cannot", "can't"]}}
    assert grade_case(decline, run("I can't rank drivers."), ctx)["passed"]
    assert not grade_case(decline, run("Max Verstappen, easily."), ctx)["passed"]
    assert not grade_case(decline, run("I can't, but it is 8.3 s.", [call("compare_strategy", {"gap_s": 1.0})]), ctx)["passed"]
    allowed = {**decline, "expect": {**decline["expect"], "allow_tool_call": True, "must_mention": ["position"]}}
    assert grade_case(allowed, run("I can't estimate finishing position.", [call("compare_strategy", {"gap_s": 1.0})]), ctx)["passed"]

    ask = {"id": "a", "group": "ask", "question": "What if he pitted on lap 20?", "expect": {"behavior": "ask"}}
    assert grade_case(ask, run("Which race and car do you mean?"), ctx)["passed"]
    assert not grade_case(ask, run("Which race?", [call("compare_strategy", race="x", car="y")]), ctx)["passed"]
    assert not grade_case(ask, run("I will assume Monza."), ctx)["passed"]

    lookup = {"id": "l", "group": "lookup", "question": "Which drivers can I pick for Monza 2024?",
              "expect": {"behavior": "lookup", "tools": ["list_cars"], "args": {"race": "Monza 2024"}}}
    assert grade_case(lookup, run("VER, LEC...", [call("list_cars", race="Monza 2024")]), ctx)["passed"]
    assert not grade_case(lookup, run("VER, LEC...", [call("list_cars", race="Monza 2023")]), ctx)["checks"]["right_arguments"]
    with pytest.raises(ValueError, match="unknown behavior"):
        grade_case({**ask, "expect": {"behavior": "shrug"}}, run("?"), ctx)


def test_summarise_counts_and_cost():
    graded = [{"group": "named", "passed": True, "checks": {"grounded": True, "called_tool": True}},
              {"group": "named", "passed": False, "checks": {"grounded": False, "called_tool": True}},
              {"group": "ask", "passed": True, "checks": {"grounded": True}}]
    runs = [run(calls=[call("a")], tokens=(500_000, 40_000)), run(calls=[call("a"), call("b")], tokens=(500_000, 60_000)), run(tokens=(0, 0))]

    result = summarise(graded, runs, "claude-sonnet-5-5")

    assert (result["cases"], result["passed"]) == (3, 2) and result["pass_rate"] == pytest.approx(2 / 3)
    assert result["by_group"] == {"named": {"cases": 2, "passed": 1}, "ask": {"cases": 1, "passed": 1}}
    assert result["by_check"]["grounded"] == {"cases": 3, "passed": 2}
    assert result["tool_calls_per_case"] == 1.0
    assert result["cost_usd"] == pytest.approx(1_000_000 * 2.00 / 1e6 + 100_000 * 10.00 / 1e6)     # $3.00
    assert summarise(graded, runs, "some-other-model")["cost_usd"] is None


def test_the_committed_question_set_is_valid(ctx):
    cases = load_cases(CASES)

    assert len(cases) == 40 and len({c["id"] for c in cases}) == 40
    assert dict(collections.Counter(c["group"] for c in cases)) == {"named": 14, "open": 6, "lookup": 5, "decline": 10, "ask": 5}
    for case in cases:
        assert case["question"].strip() and case["expect"]["behavior"] in {"answer", "lookup", "decline", "ask"}, case["id"]
        args = case["expect"].get("args")
        if args and "race" in args:
            year, circuit = resolve_race(ctx, args["race"])               # the race exists and is offered
            assert (year, circuit) in ctx["offered"], case["id"]
            if "car" in args:
                assert "error" not in resolve_car(ctx, year, circuit, args["car"]), case["id"]
            if args.get("compounds"):                                      # a valid strategy for that race
                custom_strategy(args["compounds"], args["pit_laps"], _distance(ctx, year, circuit))
