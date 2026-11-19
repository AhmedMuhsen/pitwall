"""The agent's tools, on the real committed data (data/processed/)."""
import json

import pytest

from pitwall.agent_tools import (TOOL_DEFINITIONS, compare_strategy, list_cars, list_races, load_context, resolve_car,
                                 resolve_race, run_tool)


@pytest.fixture(scope="module")
def ctx():
    return load_context(refits=6)


def test_race_names_resolve_to_circuit_and_year(ctx):
    assert resolve_race(ctx, "Monza 2024") == (2024, "Monza")
    assert resolve_race(ctx, "Italian GP 2024") == (2024, "Monza")
    assert resolve_race(ctx, "the Abu Dhabi Grand Prix 2023") == (2023, "Yas Marina Circuit")
    assert resolve_race(ctx, "Monaco 2024") == (2024, "Monte Carlo")
    assert resolve_race(ctx, "são paulo 2025") == (2025, "Interlagos")


def test_unresolvable_races_say_why(ctx):
    assert resolve_race(ctx, "Monza")["error"] == "year_needed"
    assert "no data before 2023" in resolve_race(ctx, "Monza 2022")["message"]
    assert "2022-2025 regulation period" in resolve_race(ctx, "Monza 2026")["message"]
    unknown = resolve_race(ctx, "Narnia 2024")
    assert unknown["error"] == "unknown_race" and "Monza" in unknown["circuits"]


def test_races_that_cannot_be_compared_explain_the_reason(ctx):
    cases = {"Monaco 2024": ("race_excluded", "red flag"), "Montreal 2024": ("race_excluded", "wet"),
             "Imola 2023": ("no_such_race", "no Imola 2023"), "Interlagos 2025": ("race_not_offered", "no other race at Interlagos"),
             "Montreal 2025": ("race_not_offered", "safety car can't be replayed")}
    for race, (kind, words) in cases.items():
        result = compare_strategy(ctx, race, "1", [], [])
        assert result["error"] == kind and words in result["message"], race


def test_cars_resolve_by_number_code_or_name(ctx):
    leclerc = resolve_car(ctx, 2024, "Monza", "LEC")
    assert leclerc["number"] == 16 and leclerc["team"] == "Ferrari"
    assert resolve_car(ctx, 2024, "Monza", "16") == leclerc
    assert resolve_car(ctx, 2024, "Monza", "leclerc") == leclerc
    assert resolve_car(ctx, 2024, "Monza", "Charles Leclerc") == leclerc
    missing = resolve_car(ctx, 2024, "Monza", "Nobody")
    assert missing["error"] == "car_not_found" and any("LEC" in c for c in missing["cars"])


def test_list_races_and_cars(ctx):
    races = list_races(ctx)
    assert "Monza" in races["offered"]["2024"] and "Monte Carlo 2024" in races["not_available"]
    assert "red flag" in races["not_available"]["Monte Carlo 2024"]
    cars = list_cars(ctx, "Monza 2024")
    assert cars["race"] == "Monza 2024" and any(c["acronym"] == "LEC" for c in cars["cars"])
    assert list_cars(ctx, "Monaco 2024")["error"] == "race_excluded"


def test_compare_strategy_standard_comparison(ctx):
    result = compare_strategy(ctx, "Monza 2024", "LEC", [], [])

    assert result["race"] == "Monza 2024" and result["car"].startswith("LEC")
    assert result["real_strategy"].startswith("1 stop: Medium")
    gaps = [a["gap_s"] for a in result["alternatives"]]
    assert gaps == sorted(gaps) and len(gaps) >= 4
    assert all(round(g, 1) == g for g in gaps) and round(result["model_error_s"], 1) == result["model_error_s"]
    assert "negative" in result["gap_meaning"] and len(result["caveats"]) == 3
    assert result["verdict"]["kind"] in {"agrees", "too_close", "leans", "prefers"}
    assert "your_strategy" not in result and "80%" in result["intervals"]["race_total"]
    json.dumps(result)                                   # everything is plain JSON


def test_compare_strategy_with_a_specific_strategy_answers_about_that_strategy(ctx):
    result = compare_strategy(ctx, "Monza 2024", "LEC", ["MEDIUM", "HARD"], [20])

    mine = result["your_strategy"]
    assert mine["strategy"] == "1 stop: Medium → Hard, lap 20" and mine["is_the_users_strategy"] is True
    assert "your strategy" in mine["summary"] and mine["verdict_kind"] in {"agrees", "too_close", "leans", "prefers"}
    assert any(a.get("is_the_users_strategy") for a in result["alternatives"])


def test_a_strategy_beyond_the_observed_tyre_ages_is_flagged_not_judged(ctx):
    result = compare_strategy(ctx, "Monza 2024", "LEC", ["MEDIUM", "HARD"], [8])

    assert "warning" in result["your_strategy"] and "extrapolation" in result["your_strategy"]["summary"]


def test_invalid_strategies_return_the_rule_that_was_broken(ctx):
    assert "two different dry compounds" in compare_strategy(ctx, "Monza 2024", "LEC", ["HARD", "HARD"], [20])["message"]
    assert "between 1 and" in compare_strategy(ctx, "Monza 2024", "LEC", ["MEDIUM", "HARD"], [999])["message"]
    assert "Not dry compounds" in compare_strategy(ctx, "Monza 2024", "LEC", ["INTERMEDIATE", "HARD"], [20])["message"]
    assert compare_strategy(ctx, "Monza 2024", "LEC", ["MEDIUM", "HARD"], [20])["race"] == "Monza 2024"


def test_safety_car_races_say_so(ctx):
    result = compare_strategy(ctx, "Sakhir 2025", "1", [], [])

    assert result["safety_car_replayed"] == ["safety car on laps 32 to 35"]
    assert "safety car" in result["intervals"]["race_total"] or "plus or minus 26" in result["intervals"]["race_total"]


def test_tool_definitions_are_strict_and_complete():
    assert [t["name"] for t in TOOL_DEFINITIONS] == ["list_races", "list_cars", "compare_strategy"]
    for tool in TOOL_DEFINITIONS:
        schema = tool["input_schema"]
        assert tool["strict"] is True and schema["additionalProperties"] is False
        assert sorted(schema["required"]) == sorted(schema["properties"])      # strict mode: every parameter required


def test_run_tool_never_raises(ctx):
    assert run_tool(ctx, "nope", {})["error"] == "unknown_tool"
    assert run_tool(ctx, "list_cars", {})["error"] == "bad_input"
    assert run_tool(ctx, "compare_strategy", {"race": "Monza 2024", "car": "LEC"})["race"] == "Monza 2024"   # missing lists = standard
    assert run_tool(ctx, "list_races", {})["years"] == [2023, 2024, 2025]
