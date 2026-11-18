import pytest

from pitwall.backtest import actual_strategy, backtest_race


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
