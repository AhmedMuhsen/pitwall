import pandas as pd
import pytest

from pitwall.comparison import (candidate_strategies, comparable_races, compare_driver, compare_race,
                                compare_strategies, cumulative_gap, driver_choices, fastest_by_scenario, fit_inputs,
                                gap_ranges, load_dataset, race_settings, sensitivity, verdict)
from pitwall.simulator import simulate


class StubModel:
    """delta = 0.1 * tyre_age + 1.0 * race_fraction, easy to work out by hand."""

    def predict(self, X):
        return 0.1 * X["tyre_age"].to_numpy() + 1.0 * X["race_fraction"].to_numpy()


MAX_AGES = {("X", "SOFT"): 50, ("X", "MEDIUM"): 50, ("X", "HARD"): 50}

# 4-lap race. Fuel adds (1 + 2 + 3 + 4) / 4 = 2.5 s to every strategy.
# one_stop: MEDIUM laps 1-2 (ages 0, 1), HARD laps 3-4 (ages 0, 1): wear 0.2 s, 1 stop.
# two_stop: MEDIUM lap 1 (age 0), HARD lap 2 (age 0), MEDIUM laps 3-4 (ages 0, 1): wear 0.1 s, 2 stops.
STRATEGIES = {
    "one_stop": {"compounds": ["MEDIUM", "HARD"], "pit_laps": [2]},
    "two_stop": {"compounds": ["MEDIUM", "HARD", "MEDIUM"], "pit_laps": [1, 2]},
}


def compare(pit_loss=20.0, wear_offset=0.0, strategies=STRATEGIES, baseline="one_stop"):
    return compare_strategies(strategies, 4, "X", StubModel(), reference_lap=100.0, pit_loss=pit_loss,
                              lap_one_loss=0.0, max_ages=MAX_AGES, baseline=baseline, wear_offset=wear_offset)


def test_candidate_strategies_pit_laps_for_57_laps():
    result = candidate_strategies(57)

    assert result["1stop_MH_early"]["pit_laps"] == [19]   # 57 * 0.35 = 19.95, rounded down
    assert result["1stop_MH_late"]["pit_laps"] == [28]
    assert result["1stop_HM"]["pit_laps"] == [34]
    assert result["2stop_MHH"]["pit_laps"] == [19, 38]
    assert result["2stop_SHH"]["pit_laps"] == [14, 34]


def test_candidate_strategies_rejects_too_short_race():
    with pytest.raises(ValueError):
        candidate_strategies(2)


def test_compare_strategies_hand_example():
    result = compare()

    # one_stop: 400 + 0.2 + 2.5 + 20 = 422.7; two_stop: 400 + 0.1 + 2.5 + 40 = 442.6
    assert [r["strategy"] for r in result] == ["one_stop", "two_stop"]
    assert [r["rank"] for r in result] == [1, 2]
    assert result[0]["total"] == pytest.approx(422.7)
    assert result[1]["total"] == pytest.approx(442.6)
    assert result[0]["gap"] == pytest.approx(0.0)
    assert result[1]["gap"] == pytest.approx(19.9)
    assert all(r["error"] is None and r["flags"] == [] for r in result)


def test_compare_strategies_wear_offset_adds_offset_times_summed_age():
    result = compare(wear_offset=0.05)

    # Summed tyre age: one_stop 2, two_stop 1.
    assert result[0]["total"] == pytest.approx(422.7 + 0.1)
    assert result[1]["total"] == pytest.approx(442.6 + 0.05)


def test_compare_strategies_keeps_refused_strategy_at_the_end():
    strategies = {**STRATEGIES, "one_compound": {"compounds": ["HARD", "HARD"], "pit_laps": [2]}}

    result = compare(strategies=strategies)

    assert result[-1]["strategy"] == "one_compound"
    assert result[-1]["total"] is None and result[-1]["rank"] is None
    assert "two different dry compounds" in result[-1]["error"]


def test_compare_strategies_rejects_unknown_baseline():
    with pytest.raises(ValueError, match="Baseline"):
        compare(baseline="three_stop")


def test_compare_strategies_rejects_baseline_that_cannot_be_simulated():
    strategies = {**STRATEGIES, "one_compound": {"compounds": ["HARD", "HARD"], "pit_laps": [2]}}

    with pytest.raises(ValueError, match="can't be simulated"):
        compare(strategies=strategies, baseline="one_compound")


def test_sensitivity_shows_ranking_flip_with_free_stops():
    rows = sensitivity(STRATEGIES, 4, "X", StubModel(), 100.0, {"free": 0.0, "costly": 20.0},
                       0.0, MAX_AGES, "one_stop", [0.0])

    winners = {r["pit_loss_label"]: r["strategy"] for r in rows if r["rank"] == 1}
    # With no pit loss, two_stop's lower wear wins: 402.6 vs 402.7.
    assert winners == {"free": "two_stop", "costly": "one_stop"}
    assert len(rows) == 4
    assert {r["wear_offset"] for r in rows} == {0.0}


def race_row(lap, driver, duration, clean=True, circuit="X", year=2024):
    return {"session_key": 1, "circuit": circuit, "year": year, "driver_number": driver,
            "lap_number": lap, "lap_duration": duration, "is_clean": clean}


# Two drivers, 4 clean laps each. Driver 1's median lap is 100.5, driver 2's is 102.5.
RACE = [race_row(lap, 1, d) for lap, d in zip([1, 2, 3, 4], [105.0, 100.0, 99.0, 101.0])] + \
       [race_row(lap, 2, d) for lap, d in zip([1, 2, 3, 4], [107.0, 102.0, 101.0, 103.0])]
INPUTS = {"model": StubModel(), "max_ages": MAX_AGES, "wear_range": 0.05, "lap_one_loss": {"X": 0.0},
          "pit_loss": {"X": {"q25": 0.0, "median": 20.0, "q75": 25.0}}}


def test_load_dataset_adds_delta_and_race_fraction(tmp_path):
    import pyarrow as pa
    import pyarrow.parquet as pq
    path = tmp_path / "laps.parquet"
    pq.write_table(pa.Table.from_pylist(RACE), path)

    rows = load_dataset(path)

    first = rows[0]   # driver 1, lap 1: 105.0 - median(105, 100, 99, 101) = 105.0 - 100.5
    assert first["delta"] == pytest.approx(4.5)
    assert first["race_fraction"] == pytest.approx(0.25)


def test_race_settings_hand_example():
    result = race_settings(RACE, INPUTS, "X", 2024)

    # Driver medians over all 4 clean laps: 100.5 and 102.5; their median is 101.5.
    assert result == {"race_distance": 4, "reference_lap": pytest.approx(101.5),
                      "pit_losses": {"q25": 0.0, "median": 20.0, "q75": 25.0}, "lap_one_loss": 0.0}


def test_race_settings_rejects_missing_race_and_missing_pit_loss():
    with pytest.raises(ValueError, match="No race"):
        race_settings(RACE, INPUTS, "X", 2025)
    with pytest.raises(ValueError, match="No measured pit stops"):
        race_settings(RACE, {**INPUTS, "pit_loss": {}}, "X", 2024)


def test_compare_race_returns_ranking_sensitivity_and_laps():
    result = compare_race(RACE, INPUTS, "X", 2024)

    assert result["settings"]["race_distance"] == 4
    assert len(result["ranking"]) == len(result["strategies"])
    # 3 pit losses x 3 wear offsets, every strategy in each.
    assert len(result["sensitivity"]) == 9 * len(result["strategies"])
    assert {r["wear_offset"] for r in result["sensitivity"]} == {-0.05, 0.0, 0.05}
    laps = result["laps"]
    assert set(laps["strategy"]) == set(result["strategies"])
    assert (laps.groupby("strategy")["lap_number"].max() == 4).all()


def test_fit_inputs_needs_two_training_years():
    with pytest.raises(ValueError, match="two training years"):
        fit_inputs(RACE, [2024])


def test_fastest_by_scenario_grid():
    rows = sensitivity(STRATEGIES, 4, "X", StubModel(), 100.0, {"free": 0.0, "costly": 20.0},
                       0.0, MAX_AGES, "one_stop", [0.0, 0.05])

    grid = fastest_by_scenario(rows)

    assert grid.index.tolist() == ["free", "costly"]
    assert grid.columns.tolist() == [0.0, 0.05]
    # Free stops: two_stop wins at both offsets (its summed tyre age is lower).
    assert grid.loc["free"].tolist() == ["two_stop", "two_stop"]
    assert grid.loc["costly"].tolist() == ["one_stop", "one_stop"]


def test_fastest_by_scenario_rejects_no_ranked_rows():
    with pytest.raises(ValueError):
        fastest_by_scenario([{"rank": None, "pit_loss_label": "q25", "wear_offset": 0.0, "strategy": "a"}])


def driver_lap(driver, lap, duration, compound, stint, age, reasons=(), year=2024):
    return {"session_key": 1, "circuit": "X", "year": year, "driver_number": driver, "lap_number": lap,
            "lap_duration": duration, "is_clean": duration is not None and not reasons,
            "compound": compound, "stint_number": stint, "tyre_age": age, "exclusion_reasons": list(reasons),
            "race_fraction": lap / 4}


# 4-lap race. Car 1: MEDIUM laps 1-2 (ages 0, 1), pits on lap 2, HARD laps 3-4 (ages 0, 1),
# lap times 105, 100, 99, 101 (real total 405.0, median clean lap 100.5).
# Car 2 has no time on lap 3 (left out). Car 3 has no clean lap (no reference, left out).
DRIVER_RACE = (
    [driver_lap(1, lap, d, c, s, a) for lap, d, c, s, a in
     [(1, 105.0, "MEDIUM", 1, 0), (2, 100.0, "MEDIUM", 1, 1), (3, 99.0, "HARD", 2, 0), (4, 101.0, "HARD", 2, 1)]]
    + [driver_lap(2, lap, d, "MEDIUM" if lap < 3 else "HARD", 1 if lap < 3 else 2, 0) for lap, d in
       [(1, 106.0), (2, 101.0), (3, None), (4, 102.0)]]
    + [driver_lap(3, lap, 110.0, "MEDIUM", 1, lap - 1, reasons=["traffic"]) for lap in [1, 2, 3, 4]]
)


def test_comparable_races_leaves_out_safety_car_races():
    sc_race = [{**r, "year": 2023, "exclusion_reasons": ["safety_car"]} for r in DRIVER_RACE[:1]] + \
              [{**r, "year": 2023} for r in DRIVER_RACE[1:4]]
    other = [{**r, "year": 2025, "circuit": "A"} for r in DRIVER_RACE[:4]]

    assert comparable_races(DRIVER_RACE + sc_race + other) == [(2025, "A"), (2024, "X")]


def test_driver_choices_only_full_distance_with_reference():
    assert driver_choices(DRIVER_RACE, "X", 2024) == [1]


def test_driver_choices_with_model_needs_clean_first_half_laps():
    # Car 1 has 2 clean first-half laps. Make lap 1 unclean: only 1 left, so 2 are needed -> out.
    race = [{**r, "is_clean": False} if r["driver_number"] == 1 and r["lap_number"] == 1 else r
            for r in DRIVER_RACE]

    assert driver_choices(race, "X", 2024, StubModel(), min_clean_laps=2) == []
    assert driver_choices(race, "X", 2024, StubModel(), min_clean_laps=1) == [1]
    assert driver_choices(race, "X", 2024) == [1]    # without a model, one clean lap is enough


def test_driver_choices_rejects_safety_car_race():
    race = [{**r, "exclusion_reasons": ["safety_car"]} if r["lap_number"] == 2 else r for r in DRIVER_RACE]

    with pytest.raises(ValueError, match="safety car"):
        driver_choices(race, "X", 2024)


def test_compare_driver_hand_example():
    result = compare_driver(DRIVER_RACE, INPUTS, "X", 2024, 1, min_clean_laps=2)

    assert result["actual_strategy"] == {"compounds": ["MEDIUM", "HARD"], "pit_laps": [2], "start_ages": [0, 0]}
    # Pace from laps 1-2: model deltas 0.25 and 0.6, so median(105 - 0.25, 100 - 0.6) = 102.075.
    assert result["settings"]["reference_lap"] == pytest.approx(102.075)
    assert result["actual_time"] == pytest.approx(405.0)
    # 4 * 102.075 + wear 0.2 + fuel 2.5 + one stop 20.0 = 431.0
    assert result["simulated_actual"] == pytest.approx(431.0)
    assert result["model_error"] == pytest.approx(26.0)
    gaps = {r["strategy"]: r["gap"] for r in result["ranking"]}
    assert gaps["actual"] == pytest.approx(0.0)
    # 1stop_MH_late on 4 laps pits on lap 2 with new sets: the same as the real strategy.
    assert gaps["1stop_MH_late"] == pytest.approx(0.0)
    assert result["real_laps"]["lap_time"].tolist() == [105.0, 100.0, 99.0, 101.0]
    assert "actual" in set(result["laps"]["strategy"])


def test_compare_driver_rejects_driver_without_full_race():
    with pytest.raises(ValueError, match="Car 2"):
        compare_driver(DRIVER_RACE, INPUTS, "X", 2024, 2, min_clean_laps=2)


def ranges_row(strategy, gap, low, high, confidence, flagged=False):
    return {"strategy": strategy, "gap": gap, "min_gap": low, "max_gap": high,
            "confidence": confidence, "flagged": flagged}


def test_gap_ranges_hand_example():
    rows = sensitivity(STRATEGIES, 4, "X", StubModel(), 100.0, {"free": 0.0, "costly": 20.0},
                       0.0, MAX_AGES, "one_stop", [0.0])

    result = gap_ranges(rows, "one_stop", base_pit_label="costly")

    # two_stop: +19.9 with a 20 s stop, -0.1 with free stops (see the sensitivity test above).
    assert [r["strategy"] for r in result] == ["one_stop", "two_stop"]
    assert result[0]["confidence"] == "baseline"
    two = result[1]
    assert two["gap"] == pytest.approx(19.9)
    assert (two["min_gap"], two["max_gap"]) == (pytest.approx(-0.1), pytest.approx(19.9))
    assert two["confidence"] == "depends on assumptions"
    assert two["flagged"] is False


def test_gap_ranges_slower_everywhere_and_missing_best_estimate():
    rows = sensitivity(STRATEGIES, 4, "X", StubModel(), 100.0, {"costly": 20.0}, 0.0, MAX_AGES, "one_stop", [0.0])

    assert gap_ranges(rows, "one_stop", base_pit_label="costly")[1]["confidence"] == "slower in every scenario"
    with pytest.raises(ValueError, match="best-estimate"):
        gap_ranges(rows, "one_stop")   # no "median" label in these rows


def test_verdict_tiers():
    base = ranges_row("real", 0.0, 0.0, 0.0, "baseline")
    far = ranges_row("far", -12.0, -15.0, -9.0, "faster in every scenario")
    mid = ranges_row("mid", -5.0, -8.0, 2.0, "depends on assumptions")
    near = ranges_row("near", -2.9, -4.0, -1.0, "faster in every scenario")
    slower = ranges_row("slow", 4.0, 1.0, 7.0, "slower in every scenario")

    assert verdict([base, far, mid])["kind"] == "prefers"
    assert verdict([base, far, mid])["strategy"] == "far"
    assert verdict([base, far, mid])["robust"] is True
    assert verdict([base, mid, slower])["kind"] == "leans"
    assert verdict([base, mid, slower])["robust"] is False
    assert verdict([base, near, slower])["kind"] == "too_close"
    assert verdict([base, slower]) == {"kind": "agrees", "strategy": None, "range": None, "robust": False}


def test_verdict_boundaries_and_custom_thresholds():
    base = ranges_row("real", 0.0, 0.0, 0.0, "baseline")

    assert verdict([base, ranges_row("a", -3.0, -3.0, -3.0, "faster in every scenario")])["kind"] == "leans"
    assert verdict([base, ranges_row("a", -10.0, -10.0, -10.0, "faster in every scenario")])["kind"] == "prefers"
    assert verdict([base, ranges_row("a", -5.0, -5.0, -5.0, "faster in every scenario")], close=6.0)["kind"] == "too_close"


def test_verdict_ignores_flagged_alternatives():
    base = ranges_row("real", 0.0, 0.0, 0.0, "baseline")
    flagged = ranges_row("c", -20.0, -25.0, -15.0, "faster in every scenario", flagged=True)
    mid = ranges_row("b", -5.0, -8.0, 2.0, "depends on assumptions")

    assert verdict([base, flagged, mid])["strategy"] == "b"
    assert verdict([base, flagged])["kind"] == "agrees"


def test_cumulative_gap_hand_example():
    laps = pd.concat([simulate(s, 4, "X", StubModel(), 100.0, 20.0, 0.0, MAX_AGES)["laps"]
                      [["lap_number", "lap_time"]].assign(strategy=name) for name, s in STRATEGIES.items()])

    result = cumulative_gap(laps, STRATEGIES, 20.0, "two_stop", "one_stop")

    # Lap 1: two_stop pits (+20). Lap 2: both pit; two_stop's new HARD is 0.1 s quicker. Laps 3-4 equal.
    assert result["lap_number"].tolist() == [1, 2, 3, 4]
    assert result["gap"].tolist() == pytest.approx([20.0, 19.9, 19.9, 19.9])


def test_cumulative_gap_rejects_unknown_strategy():
    laps = simulate(STRATEGIES["one_stop"], 4, "X", StubModel(), 100.0, 20.0, 0.0, MAX_AGES)["laps"]
    with pytest.raises(ValueError, match="No simulated laps"):
        cumulative_gap(laps.assign(strategy="one_stop"), STRATEGIES, 20.0, "two_stop", "one_stop")


def test_compare_driver_candidates_start_on_the_real_first_set():
    # Car 1 again, but its first MEDIUM set was already 3 laps old at the start.
    race = [{**r, "tyre_age": r["tyre_age"] + 3} if r["driver_number"] == 1 and r["stint_number"] == 1 else r
            for r in DRIVER_RACE]

    strategies = compare_driver(race, INPUTS, "X", 2024, 1, min_clean_laps=2)["strategies"]

    assert strategies["actual"]["start_ages"] == [3, 0]
    assert strategies["1stop_MH_late"]["start_ages"] == [3, 0]     # starts on MEDIUM, like car 1
    assert strategies["2stop_MHH"]["start_ages"] == [3, 0, 0]
    assert strategies["1stop_HM"]["start_ages"] == [0, 0]          # starts on HARD: a new set
    assert strategies["2stop_SHH"]["start_ages"] == [0, 0, 0]
