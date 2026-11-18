import numpy as np
import pandas as pd
import pytest

from pitwall.model import build_pipeline
from pitwall.simulator import (observed_max_ages, simulate, stint_range_flags, strategy_laps,
                               validate_strategy)


class StubModel:
    """delta = 0.1 * tyre_age + 1.0 * race_fraction, easy to work out by hand."""

    def predict(self, X):
        return 0.1 * X["tyre_age"].to_numpy() + 1.0 * X["race_fraction"].to_numpy()


class NanModel:
    def predict(self, X):
        return np.full(len(X), np.nan)


def test_strategy_laps_hand_example():
    # 6-lap race: MEDIUM (new) for laps 1-2, pit on lap 2, then a used HARD set (3 laps old) for laps 3-6.
    strategy = {"compounds": ["MEDIUM", "HARD"], "pit_laps": [2], "start_ages": [0, 3]}

    result = strategy_laps(strategy, race_distance=6, circuit="Hungaroring")

    assert result["lap_number"].tolist() == [1, 2, 3, 4, 5, 6]
    assert result["stint"].tolist() == [1, 1, 2, 2, 2, 2]
    assert result["compound"].tolist() == ["MEDIUM", "MEDIUM", "HARD", "HARD", "HARD", "HARD"]
    assert result["tyre_age"].tolist() == [0, 1, 3, 4, 5, 6]
    assert result["race_fraction"].tolist() == pytest.approx([1/6, 2/6, 3/6, 4/6, 5/6, 1.0])
    assert set(result["circuit"]) == {"Hungaroring"}


def test_tyre_age_resets_at_stop_but_race_fraction_does_not():
    strategy = {"compounds": ["SOFT", "HARD"], "pit_laps": [3]}

    result = strategy_laps(strategy, race_distance=5, circuit="Monza")

    # New sets by default: age goes 0,1,2 then back to 0 after the stop.
    assert result["tyre_age"].tolist() == [0, 1, 2, 0, 1]
    assert result["race_fraction"].is_monotonic_increasing
    assert result["race_fraction"].iloc[3] > result["race_fraction"].iloc[2]


def test_strategy_laps_rejects_pit_laps_not_matching_compounds():
    strategy = {"compounds": ["MEDIUM", "HARD"], "pit_laps": [10, 20]}

    with pytest.raises(ValueError, match="pit_laps"):
        strategy_laps(strategy, race_distance=30, circuit="Monza")


# Ranges for the simulate tests, wide enough that only the test's own point fails.
SIM_MAX_AGES = {("Hungaroring", "MEDIUM"): 30, ("Hungaroring", "HARD"): 40,
                ("Monza", "SOFT"): 20, ("Monza", "HARD"): 30}


def test_simulate_hand_example():
    # Same 6-lap strategy as above. Deltas (0.1*age + lap/6):
    # 0.1667, 0.4333, 0.8, 1.0667, 1.3333, 1.6 -> sum 5.4
    # total = 6 * 80.0 + 5.4 + 1 stop * 20.0 = 505.4
    strategy = {"compounds": ["MEDIUM", "HARD"], "pit_laps": [2], "start_ages": [0, 3]}

    result = simulate(strategy, race_distance=6, circuit="Hungaroring", model=StubModel(),
                      reference_lap=80.0, pit_loss=20.0, lap_one_loss=0.0, max_ages=SIM_MAX_AGES)

    assert result["laps"]["predicted_delta"].tolist() == pytest.approx(
        [1/6, 0.1 + 2/6, 0.8, 0.4 + 4/6, 0.5 + 5/6, 1.6])
    assert result["laps"]["lap_time"].iloc[0] == pytest.approx(80.0 + 1/6)
    assert result["pit_stops"] == 1
    assert result["total_time"] == pytest.approx(505.4, abs=1e-3)
    assert result["flags"] == []


def test_simulate_raises_on_compound_model_never_saw():
    train = pd.DataFrame({"compound": ["SOFT", "SOFT"], "tyre_age": [0, 5], "delta": [0.0, 0.5]})
    model = build_pipeline(False).fit(train, train["delta"])
    strategy = {"compounds": ["SOFT", "HARD"], "pit_laps": [2]}

    with pytest.raises(ValueError, match="HARD"):
        simulate(strategy, race_distance=4, circuit="Monza", model=model,
                 reference_lap=80.0, pit_loss=20.0, lap_one_loss=0.0, max_ages=SIM_MAX_AGES)


def test_simulate_raises_on_missing_prediction():
    strategy = {"compounds": ["SOFT", "HARD"], "pit_laps": [2]}

    with pytest.raises(ValueError, match="missing"):
        simulate(strategy, race_distance=4, circuit="Monza", model=NanModel(),
                 reference_lap=80.0, pit_loss=20.0, lap_one_loss=0.0, max_ages=SIM_MAX_AGES)


def test_simulate_adds_lap_one_loss_to_lap_one_only():
    strategy = {"compounds": ["MEDIUM", "HARD"], "pit_laps": [2], "start_ages": [0, 3]}
    base = simulate(strategy, race_distance=6, circuit="Hungaroring", model=StubModel(),
                    reference_lap=80.0, pit_loss=20.0, lap_one_loss=0.0, max_ages=SIM_MAX_AGES)
    with_start = simulate(strategy, race_distance=6, circuit="Hungaroring", model=StubModel(),
                          reference_lap=80.0, pit_loss=20.0, lap_one_loss=5.0, max_ages=SIM_MAX_AGES)

    assert with_start["total_time"] == pytest.approx(base["total_time"] + 5.0)
    assert (with_start["laps"]["lap_time"] - base["laps"]["lap_time"]).tolist() == pytest.approx(
        [5.0, 0, 0, 0, 0, 0])


def test_simulate_returns_range_flags():
    # Monza SOFT seen to age 20; a 30-lap race on SOFT then 1 lap of HARD reaches age 28.
    strategy = {"compounds": ["SOFT", "HARD"], "pit_laps": [30]}

    result = simulate(strategy, race_distance=31, circuit="Monza", model=StubModel(),
                      reference_lap=80.0, pit_loss=20.0, lap_one_loss=0.0, max_ages=SIM_MAX_AGES)

    assert len(result["flags"]) == 1 and "SOFT@Monza" in result["flags"][0]
    assert result["total_time"] > 0


def test_simulate_refuses_invalid_strategy():
    strategy = {"compounds": ["HARD", "HARD"], "pit_laps": [2]}

    with pytest.raises(ValueError, match="two different dry compounds"):
        simulate(strategy, race_distance=4, circuit="Monza", model=StubModel(),
                 reference_lap=80.0, pit_loss=20.0, lap_one_loss=0.0, max_ages=SIM_MAX_AGES)


def test_validate_strategy_accepts_normal_two_stop():
    strategy = {"compounds": ["MEDIUM", "HARD", "MEDIUM"], "pit_laps": [21, 49], "start_ages": [0, 1, 1]}

    validate_strategy(strategy, race_distance=70)  # no error


@pytest.mark.parametrize("strategy, message", [
    ({"compounds": ["HARD", "HARD"], "pit_laps": [30]}, "two different dry compounds"),
    ({"compounds": ["SOFT", "INTERMEDIATE"], "pit_laps": [30]}, "INTERMEDIATE"),
    ({"compounds": ["SOFT", "HARD"], "pit_laps": [30, 40]}, "pit_laps"),
    ({"compounds": ["SOFT", "MEDIUM", "HARD"], "pit_laps": [40, 20]}, "increasing"),
    ({"compounds": ["SOFT", "MEDIUM", "HARD"], "pit_laps": [20, 20]}, "increasing"),
    ({"compounds": ["SOFT", "HARD"], "pit_laps": [0]}, "between 1 and 69"),
    ({"compounds": ["SOFT", "HARD"], "pit_laps": [70]}, "between 1 and 69"),
    ({"compounds": ["SOFT", "HARD"], "pit_laps": [30], "start_ages": [0]}, "start_ages"),
    ({"compounds": ["SOFT", "HARD"], "pit_laps": [30], "start_ages": [0, -1]}, "start_ages"),
])
def test_validate_strategy_rejects_impossible(strategy, message):
    with pytest.raises(ValueError, match=message):
        validate_strategy(strategy, race_distance=70)


def test_validate_strategy_rejects_tiny_race_distance():
    with pytest.raises(ValueError, match="race_distance"):
        validate_strategy({"compounds": ["SOFT", "HARD"], "pit_laps": [1]}, race_distance=1)


def test_observed_max_ages_takes_highest_over_chosen_years():
    table = {("X", 2023, "HARD"): 38, ("X", 2024, "HARD"): 40, ("X", 2025, "HARD"): 54,
             ("X", 2023, "SOFT"): 5}

    result = observed_max_ages(table, years=[2023, 2024])

    assert result == {("X", "HARD"): 40, ("X", "SOFT"): 5}


MAX_AGES = {("X", "SOFT"): 10, ("X", "HARD"): 20}


def test_stint_range_flags_none_within_range():
    strategy = {"compounds": ["SOFT", "HARD"], "pit_laps": [11]}  # HARD laps 12-30, ages 0-18

    assert stint_range_flags(strategy, race_distance=30, circuit="X", max_ages=MAX_AGES) == []


def test_stint_range_flags_ignores_in_lap_age():
    # SOFT pit on lap 12: ages 0-11, lap 12 (age 11) is the in-lap; age 10 is the last racing lap = max.
    ok = {"compounds": ["SOFT", "HARD"], "pit_laps": [12]}
    # Pit on lap 13: last racing lap is age 11 > 10.
    over = {"compounds": ["SOFT", "HARD"], "pit_laps": [13]}

    assert stint_range_flags(ok, race_distance=30, circuit="X", max_ages=MAX_AGES) == []
    flags = stint_range_flags(over, race_distance=30, circuit="X", max_ages=MAX_AGES)
    assert len(flags) == 1
    assert "SOFT@X" in flags[0] and "11" in flags[0] and "10" in flags[0]


def test_stint_range_flags_final_stint_counts_last_lap():
    strategy = {"compounds": ["SOFT", "HARD"], "pit_laps": [11]}  # HARD laps 12-35, ages 0-23

    flags = stint_range_flags(strategy, race_distance=35, circuit="X", max_ages=MAX_AGES)

    assert len(flags) == 1
    assert "Stint 2" in flags[0] and "HARD@X" in flags[0] and "23" in flags[0] and "20" in flags[0]


def test_stint_range_flags_refuses_pair_with_no_data():
    strategy = {"compounds": ["SOFT", "MEDIUM"], "pit_laps": [5]}

    with pytest.raises(ValueError, match="MEDIUM@X"):
        stint_range_flags(strategy, race_distance=30, circuit="X", max_ages=MAX_AGES)
