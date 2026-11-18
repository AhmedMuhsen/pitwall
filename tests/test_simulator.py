import numpy as np
import pandas as pd
import pytest

from pitwall.model import build_pipeline
from pitwall.simulator import simulate, strategy_laps


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


def test_simulate_hand_example():
    # Same 6-lap strategy as above. Deltas (0.1*age + lap/6):
    # 0.1667, 0.4333, 0.8, 1.0667, 1.3333, 1.6 -> sum 5.4
    # total = 6 * 80.0 + 5.4 + 1 stop * 20.0 = 505.4
    strategy = {"compounds": ["MEDIUM", "HARD"], "pit_laps": [2], "start_ages": [0, 3]}

    result = simulate(strategy, race_distance=6, circuit="Hungaroring", model=StubModel(),
                      reference_lap=80.0, pit_loss=20.0)

    assert result["laps"]["predicted_delta"].tolist() == pytest.approx(
        [1/6, 0.1 + 2/6, 0.8, 0.4 + 4/6, 0.5 + 5/6, 1.6])
    assert result["laps"]["lap_time"].iloc[0] == pytest.approx(80.0 + 1/6)
    assert result["pit_stops"] == 1
    assert result["total_time"] == pytest.approx(505.4, abs=1e-3)


def test_simulate_raises_on_compound_model_never_saw():
    train = pd.DataFrame({"compound": ["SOFT", "SOFT"], "tyre_age": [0, 5], "delta": [0.0, 0.5]})
    model = build_pipeline(False).fit(train, train["delta"])
    strategy = {"compounds": ["SOFT", "HARD"], "pit_laps": [2]}

    with pytest.raises(ValueError, match="HARD"):
        simulate(strategy, race_distance=4, circuit="Monza", model=model,
                 reference_lap=80.0, pit_loss=20.0)


def test_simulate_raises_on_missing_prediction():
    strategy = {"compounds": ["SOFT", "HARD"], "pit_laps": [2]}

    with pytest.raises(ValueError, match="missing"):
        simulate(strategy, race_distance=4, circuit="Monza", model=NanModel(),
                 reference_lap=80.0, pit_loss=20.0)
