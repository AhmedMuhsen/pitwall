import pandas as pd
import pytest

from pitwall.backtest import (actual_strategy, backtest_race, error_components, second_half_record,
                              stint_holdout_errors, strategy_pair_errors)


class StubModel:
    """delta = 0.1 * tyre_age + 1.0 * race_fraction."""

    def predict(self, X):
        return 0.1 * X["tyre_age"].to_numpy() + 1.0 * X["race_fraction"].to_numpy()


def race_lap(driver, lap, duration, stint, compound, age, clean, reasons=()):
    return {"session_key": 1, "driver_number": driver, "lap_number": lap, "lap_duration": duration,
            "stint_number": stint, "compound": compound, "tyre_age": age, "is_clean": clean,
            "circuit": "X", "year": 2024, "exclusion_reasons": list(reasons)}


def test_actual_strategy_rebuilds_compounds_pit_laps_and_used_set_ages():
    laps = [  # deliberately out of order
        race_lap(1, 4, 81.0, 2, "HARD", 0, True),
        race_lap(1, 1, 95.0, 1, "MEDIUM", 2, False),
        race_lap(1, 2, 80.0, 1, "MEDIUM", 3, True),
        race_lap(1, 3, 90.0, 1, "MEDIUM", 4, False),
        race_lap(1, 5, 81.0, 2, "HARD", 1, True),
    ]

    assert actual_strategy(laps) == {"compounds": ["MEDIUM", "HARD"], "pit_laps": [3], "start_ages": [2, 0]}


def test_actual_strategy_raises_on_lap_without_stint():
    laps = [race_lap(1, 1, 95.0, 1, "MEDIUM", 0, False), race_lap(1, 2, 80.0, None, None, None, False)]

    with pytest.raises(ValueError, match="stint"):
        actual_strategy(laps)


MAX_AGES = {("X", "SOFT"): 10, ("X", "HARD"): 10}


def test_backtest_race_hand_example():
    rows = [
        # Driver 1: full distance. Reference = median of clean laps 2 and 4 = 80.5.
        # Predicted deltas 0.25, 0.6, 0.75, 1.1 (sum 2.7); total 4*80.5 + 2.7 + 20 + 5 = 349.7.
        race_lap(1, 1, 95.0, 1, "SOFT", 0, False, ["lap_1"]),
        race_lap(1, 2, 80.0, 1, "SOFT", 1, True),
        race_lap(1, 3, 101.0, 2, "HARD", 0, False, ["pit_out"]),
        race_lap(1, 4, 81.0, 2, "HARD", 1, True),
        # Driver 2: lapped (3 laps), skipped.
        race_lap(2, 1, 96.0, 1, "SOFT", 0, False, ["lap_1"]),
        race_lap(2, 2, 82.0, 1, "SOFT", 1, True),
        race_lap(2, 3, 83.0, 1, "SOFT", 2, True),
    ]

    result = {r["driver_number"]: r for r in backtest_race(rows, StubModel(), pit_loss=20.0,
                                                           lap_one_loss=5.0, max_ages=MAX_AGES)}

    assert result[1]["predicted"] == pytest.approx(349.7)
    assert result[1]["actual"] == pytest.approx(357.0)
    assert result[1]["error"] == pytest.approx(-7.3)
    assert result[1]["laps"] == 4 and result[1]["flags"] == [] and result[1]["skip_reason"] is None
    assert result[2]["predicted"] is None and result[2]["skip_reason"] == "not_full_distance"


def test_backtest_race_records_strategy_it_cannot_simulate():
    rows = [  # one compound only: fails validate_strategy
        race_lap(1, 1, 95.0, 1, "SOFT", 0, False, ["lap_1"]),
        race_lap(1, 2, 80.0, 1, "SOFT", 1, True),
    ]

    [record] = backtest_race(rows, StubModel(), pit_loss=20.0, lap_one_loss=5.0, max_ages=MAX_AGES)

    assert record["predicted"] is None
    assert record["skip_reason"].startswith("cannot_simulate") and "two different" in record["skip_reason"]


def test_backtest_race_refuses_race_with_safety_car():
    rows = [race_lap(1, 1, 95.0, 1, "SOFT", 0, False, ["lap_1", "safety_car"])]

    with pytest.raises(ValueError, match="safety"):
        backtest_race(rows, StubModel(), pit_loss=20.0, lap_one_loss=5.0, max_ages=MAX_AGES)


def test_backtest_race_skips_driver_with_no_clean_lap():
    rows = [
        race_lap(1, 1, 95.0, 1, "SOFT", 0, False, ["lap_1"]),
        race_lap(1, 2, 80.0, 2, "HARD", 0, False, ["pit_out"]),
    ]

    [record] = backtest_race(rows, StubModel(), pit_loss=20.0, lap_one_loss=5.0, max_ages=MAX_AGES)

    assert record["predicted"] is None and record["skip_reason"] == "no_reference"


def test_error_components_hand_example():
    # Pit on lap 2: lap 2 is the in-lap, lap 3 the out-lap, lap 4 normal.
    actual = [race_lap(1, n, d, 1, "SOFT", 0, False) for n, d in ((1, 95.0), (2, 80.0), (3, 101.0), (4, 81.0))]
    simulated = pd.DataFrame({"lap_number": [1, 2, 3, 4], "lap_time": [85.75, 81.1, 81.25, 81.6]})

    parts = error_components(actual, simulated, pit_laps=[2], pit_loss=20.0)

    assert parts["lap_one"] == pytest.approx(-9.25)
    assert parts["stops"] == pytest.approx(1.1 - 19.75 + 20.0)
    assert parts["normal"] == pytest.approx(0.6)
    assert parts["normal_by_lap"] == {4: pytest.approx(0.6)}


def test_error_components_driver_with_no_stops():
    actual = [race_lap(1, n, d, 1, "SOFT", 0, False) for n, d in ((1, 90.0), (2, 80.0), (3, 81.0))]
    simulated = pd.DataFrame({"lap_number": [1, 2, 3], "lap_time": [88.0, 80.5, 80.5]})

    parts = error_components(actual, simulated, pit_laps=[], pit_loss=20.0)

    assert parts["stops"] == 0
    assert parts["lap_one"] == pytest.approx(-2.0)
    assert parts["normal_by_lap"] == {2: pytest.approx(0.5), 3: pytest.approx(-0.5)}


def test_error_components_raises_when_laps_dont_match():
    actual = [race_lap(1, 1, 90.0, 1, "SOFT", 0, False)]
    simulated = pd.DataFrame({"lap_number": [1, 2], "lap_time": [88.0, 80.5]})

    with pytest.raises(ValueError, match="match"):
        error_components(actual, simulated, pit_laps=[], pit_loss=20.0)


def test_backtest_race_components_add_up_to_error():
    rows = [
        race_lap(1, 1, 95.0, 1, "SOFT", 0, False, ["lap_1"]),
        race_lap(1, 2, 80.0, 1, "SOFT", 1, True),
        race_lap(1, 3, 101.0, 2, "HARD", 0, False, ["pit_out"]),
        race_lap(1, 4, 81.0, 2, "HARD", 1, True),
    ]

    [record] = backtest_race(rows, StubModel(), pit_loss=20.0, lap_one_loss=5.0, max_ages=MAX_AGES)

    parts = record["components"]
    assert parts["lap_one"] + parts["stops"] + parts["normal"] == pytest.approx(record["error"])


MAX_AGES_X = {("X", "MEDIUM"): 50, ("X", "HARD"): 50}


def half_lap(lap, duration, stint, compound, age, clean=True):
    return {**race_lap(1, lap, duration, stint, compound, age, clean), "race_fraction": lap / 4}


def test_second_half_record_hand_example():
    # 4 laps; first half = laps 1-2. MEDIUM laps 1-2 (ages 0, 1), pit on lap 2, HARD laps 3-4 (ages 0, 1).
    laps = [half_lap(1, 105.0, 1, "MEDIUM", 0), half_lap(2, 100.0, 1, "MEDIUM", 1),
            half_lap(3, 99.0, 2, "HARD", 0), half_lap(4, 101.0, 2, "HARD", 1)]

    result = second_half_record(laps, StubModel(), 4, pit_loss=20.0, max_ages=MAX_AGES_X, min_clean_laps=2)

    # Pace: predicted deltas on laps 1-2 are 0.25 and 0.6, so median(104.75, 99.4) = 102.075.
    assert result["pace"] == pytest.approx(102.075)
    assert result["real"] == pytest.approx(200.0)
    # Laps 3-4: 2 * 102.075 + (0.0 + 0.75) + (0.1 + 1.0); the stop is on lap 2, so not scored.
    assert result["predicted"] == pytest.approx(206.0)
    assert (result["stops"], result["scored_laps"], result["skip_reason"]) == (0, 2, None)


def test_second_half_record_skips_too_few_first_half_clean_laps():
    laps = [half_lap(1, 105.0, 1, "MEDIUM", 0, clean=False), half_lap(2, 100.0, 1, "MEDIUM", 1),
            half_lap(3, 99.0, 2, "HARD", 0), half_lap(4, 101.0, 2, "HARD", 1)]

    result = second_half_record(laps, StubModel(), 4, 20.0, MAX_AGES_X, min_clean_laps=2)

    assert result["skip_reason"] == "too_few_first_half_laps"
    assert result["predicted"] is None


def pair_record(car, pace, real, predicted, stops, pit_laps, session=1, skip=None):
    return {"session_key": session, "circuit": "X", "year": 2024, "driver_number": car, "pace": pace,
            "scored_laps": 2, "real": real, "predicted": predicted, "stops": stops, "pit_loss": 20.0,
            "strategy": {"compounds": ["MEDIUM", "HARD"], "pit_laps": pit_laps}, "skip_reason": skip}


def test_strategy_pair_errors_hand_example():
    records = [
        pair_record(1, 100.0, 205.0, 203.0, 1, [3]),
        pair_record(2, 101.0, 204.0, 206.0, 0, [10]),
        pair_record(3, 100.0, 210.0, 210.0, 1, [5]),           # same strategy as car 1 (within 3 laps)
        pair_record(4, 100.0, 210.0, 210.0, 0, [1], skip="too_few_first_half_laps"),
        pair_record(5, 100.0, 210.0, 210.0, 0, [1], session=2),  # another race: never paired
    ]

    pairs = strategy_pair_errors(records)

    assert [(p["car_a"], p["car_b"]) for p in pairs] == [(1, 2), (2, 3)]
    first = pairs[0]
    # Pace gap (100 - 101) * 2 = -2. Real: (205 - 204) + 2 = 3. Predicted: (203 - 206) + 2 = -1.
    assert first["real"] == pytest.approx(3.0)
    assert first["predicted"] == pytest.approx(-1.0)
    assert first["error"] == pytest.approx(-4.0)
    assert first["stops_only"] == pytest.approx(20.0)


def stint_lap(lap, duration, stint, age, clean=True):
    return {**half_lap(lap, duration, stint, "MEDIUM", age, clean), "lap_duration": duration}


# 4 laps, two stints. Model deltas (0.1 * age + race_fraction): lap 1 0.25, lap 2 0.6, lap 3 0.75, lap 4 1.1.
TWO_STINTS = [stint_lap(1, 100.0, 1, 0), stint_lap(2, 100.0, 1, 1), stint_lap(3, 99.0, 2, 0), stint_lap(4, 99.0, 2, 1)]


def test_stint_holdout_errors_hand_example():
    result = stint_holdout_errors(TWO_STINTS, StubModel(), min_laps=2)

    first, last = result
    assert (first["position"], last["position"], first["n_stints"]) == ("first", "last", 2)
    # Stint 1 from stint 2: adjusted laps 98.25 and 97.9 -> pace 98.075; predicted 98.325 and 98.675
    # against 100.0 and 100.0 -> errors -1.675 and -1.325.
    assert first["error_total"] == pytest.approx(-3.0)
    assert first["error_per_lap"] == pytest.approx(-1.5)
    assert first["flat_total"] == pytest.approx(-2.0)            # the other stint's median lap is 99.0
    # Stint 2 from stint 1: adjusted laps 99.75 and 99.4 -> pace 99.575; predicted 100.325 and 100.675 vs 99.0.
    assert last["error_total"] == pytest.approx(3.0)
    assert last["flat_total"] == pytest.approx(2.0)


def test_stint_holdout_errors_takes_traffic_out_of_the_pace_and_adds_it_back():
    # Laps 3 and 4 carry a 1.0 s traffic penalty: stint 2's adjusted laps become 97.25 and 96.9, so the pace
    # for stint 1 is 97.075 and its predicted laps are 97.325 and 97.675 (no penalty on laps 1-2).
    result = stint_holdout_errors(TWO_STINTS, StubModel(), min_laps=2, penalties={3: 1.0, 4: 1.0})

    assert result[0]["error_total"] == pytest.approx(-5.0)


def test_stint_holdout_errors_needs_two_usable_stints():
    one_stint = [stint_lap(lap, 100.0, 1, lap - 1) for lap in (1, 2, 3, 4)]
    short_second = [stint_lap(1, 100.0, 1, 0), stint_lap(2, 100.0, 1, 1), stint_lap(3, 99.0, 2, 0)]
    unclean = [stint_lap(1, 100.0, 1, 0), stint_lap(2, 100.0, 1, 1), stint_lap(3, 99.0, 2, 0, clean=False),
               stint_lap(4, 99.0, 2, 1, clean=False)]

    assert stint_holdout_errors(one_stint, StubModel(), min_laps=2) == []
    assert stint_holdout_errors(short_second, StubModel(), min_laps=2) == []     # stint 2 has one clean lap
    assert stint_holdout_errors(unclean, StubModel(), min_laps=2) == []
    assert stint_holdout_errors([], StubModel()) == []
