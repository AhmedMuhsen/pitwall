"""Deterministic grading of the what-if agent: did it call the right tool with the right arguments, is every number it states
in a tool result, and does it decline or ask when it should? No second model acts as judge, so a run is easy to reproduce
and to audit. The questions are in evals/agent_questions.jsonl.
"""
import json
import re
from collections import defaultdict
from pathlib import Path

from pitwall.agent_tools import resolve_car, resolve_race

NUMBER = re.compile(r"\d+(?:[:.]\d+)*")
FORBIDDEN = ("optimal", "guarantee", "definitely", "certainly the best", "the best strategy", "perfect strategy")
NEGATIONS = ("not ", "n't", "cannot", "never", "no ", "without", "rather than", "nor ")
DECLINE_CUES = ("can't", "cannot", "can not", "unable", "not able", "isn't", "is not", "doesn't", "does not", "don't",
                "not available", "no data", "outside", "only covers", "not something", "won't", "unfortunately")
PRICES = {"claude-haiku-5-5": (0.10, 0.50), "claude-sonnet-5-5": (2.00, 10.00), "claude-opus-5-5": (4.00, 20.00),
          "anthropic/claude-haiku-5.5": (0.10, 0.50), "anthropic/claude-sonnet-5.5": (2.00, 10.00),
          "anthropic/claude-opus-5.5": (4.00, 20.00)}   # $ per 1M tokens (OpenRouter's list matched these on 2026-11-18)


def load_cases(path: Path) -> list[dict]:
    """The questions, one JSON object per line: id, group, question, expect."""
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def numbers_in(text: str) -> list[str]:
    '''Numeric tokens in a text, e.g. "5.3 s", "1:14:41.1" and "20 of 20" give ["5.3", "1:14:41.1", "20", "20"].'''
    return NUMBER.findall(text)


def _ignorable(token: str) -> bool:
    """Small whole numbers (counts like "2 stops") and years carry no claim worth tracing."""
    return token.isdigit() and (int(token) <= 10 or 2022 <= int(token) <= 2026)


def ungrounded_numbers(answer: str, question: str, tool_results: list) -> list[str]:
    '''
    Numbers in an answer that appear neither in the question nor in any tool result.

    answer, question: text
    tool_results: the tool results (any JSON-serialisable values)

    returns: the offending tokens in order. A number matches if it equals a source number within rounding (a source 8.3
    may be written "8" or "8.3"), a clock time matches if it is a prefix of a source clock time ("1:14:41" for "1:14:41.1"),
    and whole numbers up to 10 and years are ignored.
    '''
    source = numbers_in(question) + numbers_in(json.dumps(tool_results, ensure_ascii=False))
    clocks = [s for s in source if ":" in s]
    values = [float(s) for s in source if ":" not in s]
    bad = []
    for token in numbers_in(answer):
        if _ignorable(token):
            continue
        if ":" in token:
            ok = any(c == token or c.startswith(token + ".") for c in clocks)
        else:
            value = float(token)
            ok = any(abs(value - v) <= 0.051 or ("." not in token and round(v) == value) for v in values)
        if not ok:
            bad.append(token)
    return bad


def forbidden_phrases(answer: str) -> list[str]:
    '''
    Claims the agent must never make (that a strategy is optimal, best or guaranteed).

    returns: the forbidden phrases that appear without a negation just before them, so "I can't say which is optimal" passes
    and "this is the optimal strategy" fails.
    '''
    lower = answer.lower()
    found = []
    for phrase in FORBIDDEN:
        for match in re.finditer(re.escape(phrase), lower):
            window = lower[max(0, match.start() - 60):match.start()]
            if not any(negation in window for negation in NEGATIONS):
                found.append(phrase)
                break
    return found


def _args_match(ctx: dict, expected: dict, given: dict) -> bool:
    """Whether a tool call's arguments mean what the case expects (race and car compared after resolution)."""
    if "race" in expected:
        want, got = resolve_race(ctx, expected["race"]), resolve_race(ctx, str(given.get("race", "")))
        if want != got:
            return False
        if "car" in expected and want and not isinstance(want, dict):
            a, b = resolve_car(ctx, *want, expected["car"]), resolve_car(ctx, *want, str(given.get("car", "")))
            if a != b or "error" in a:
                return False
    if "compounds" in expected or "pit_laps" in expected:
        if [str(c).upper() for c in given.get("compounds") or []] != expected.get("compounds", []):
            return False
        if [int(p) for p in given.get("pit_laps") or []] != expected.get("pit_laps", []):
            return False
    return True


def grade_case(case: dict, run: dict, ctx: dict) -> dict:
    '''
    Grades one agent run against one case.

    case: {"id", "group", "question", "expect": {"behavior", ...}}; behaviors:
        "answer": call compare_strategy ("tool") with the expected "args" (race, car, compounds, pit_laps) and succeed
        "lookup": call one of the tools in "tools" (and, if "args" is given, with those arguments)
        "decline": say it can't (and mention any of "must_mention"); not give a comparison unless "allow_tool_call"
        "ask": ask a question and not call compare_strategy
    run: agent.run_agent result

    returns: {"id", "group", "checks": {name: bool}, "passed": bool, "problems": [str]}; every case is also checked for
    finishing, forbidden wording and ungrounded numbers.
    '''
    expect, answer, calls = case["expect"], run["answer"], run["tool_calls"]
    behavior = expect["behavior"]
    checks, problems = {}, []
    checks["finished"] = run["stop_reason"] == "end_turn" and bool(answer.strip())
    checks["clean_wording"] = not forbidden_phrases(answer)
    bad = ungrounded_numbers(answer, case["question"], [c["result"] for c in calls])
    checks["grounded"] = not bad
    if bad:
        problems.append(f"numbers not in any tool result: {bad}")
    compares = [c for c in calls if c["name"] == "compare_strategy"]
    successes = [c for c in compares if "error" not in c["result"]]

    if behavior == "answer":
        matching = [c for c in compares if _args_match(ctx, expect["args"], c["input"])]
        checks["called_tool"] = bool(compares)
        checks["right_arguments"] = bool(matching)
        checks["tool_succeeded"] = any("error" not in c["result"] for c in matching)
        if compares and not matching:
            problems.append(f"arguments {compares[0]['input']} do not match {expect['args']}")
    elif behavior == "lookup":
        wanted = [c for c in calls if c["name"] in expect["tools"]]
        checks["called_tool"] = bool(wanted)
        if "args" in expect:
            checks["right_arguments"] = any(_args_match(ctx, expect["args"], c["input"]) for c in wanted)
    elif behavior == "decline":
        lower = answer.lower()
        checks["declines"] = any(cue in lower for cue in DECLINE_CUES)
        if expect.get("must_mention"):
            checks["explains_why"] = any(word in lower for word in expect["must_mention"])
        if not expect.get("allow_tool_call"):
            checks["no_comparison_given"] = not successes
    elif behavior == "ask":
        checks["asks_a_question"] = "?" in answer
        checks["did_not_compare"] = not compares
    else:
        raise ValueError(f"unknown behavior {behavior!r} in case {case['id']}")
    failed = [name for name, ok in checks.items() if not ok]
    return {"id": case["id"], "group": case["group"], "checks": checks, "passed": not failed,
            "problems": problems + [f"failed: {name}" for name in failed]}


def summarise(graded: list[dict], runs: list[dict], model: str) -> dict:
    '''
    Pass rates and cost over a set of graded runs.

    graded: grade_case results; runs: the matching run_agent results; model: the model id (for the price table)

    returns: {"cases", "passed", "pass_rate", "by_group": {group: {"cases", "passed"}}, "by_check": {check: {"cases",
    "passed"}}, "tool_calls_per_case", "input_tokens", "output_tokens", "cost_usd": the provider's reported cost if every run has
    one, else an estimate from list prices (Anthropic model ids), else None}.
    '''
    by_group: defaultdict[str, list[int]] = defaultdict(lambda: [0, 0])
    by_check: defaultdict[str, list[int]] = defaultdict(lambda: [0, 0])
    for item in graded:
        by_group[item["group"]][0] += 1
        by_group[item["group"]][1] += item["passed"]
        for name, ok in item["checks"].items():
            by_check[name][0] += 1
            by_check[name][1] += ok
    tokens_in = sum(r["usage"]["input_tokens"] for r in runs)
    tokens_out = sum(r["usage"]["output_tokens"] for r in runs)
    reported = [r["usage"].get("cost_usd") for r in runs]
    price = PRICES.get(model)
    passed = sum(item["passed"] for item in graded)
    if runs and all(c is not None for c in reported):
        cost = sum(reported)                                  # what the provider billed
    elif price is not None:
        cost = (tokens_in * price[0] + tokens_out * price[1]) / 1_000_000    # estimate from list prices
    else:
        cost = None
    return {"cases": len(graded), "passed": passed, "pass_rate": passed / len(graded) if graded else 0.0,
            "by_group": {g: {"cases": n, "passed": p} for g, (n, p) in by_group.items()},
            "by_check": {c: {"cases": n, "passed": p} for c, (n, p) in by_check.items()},
            "tool_calls_per_case": sum(len(r["tool_calls"]) for r in runs) / len(runs) if runs else 0.0,
            "input_tokens": tokens_in, "output_tokens": tokens_out,
            "cost_usd": cost}
