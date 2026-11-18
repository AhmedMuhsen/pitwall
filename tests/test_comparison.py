import pytest

from pitwall.comparison import candidate_strategies, compare_strategies, sensitivity


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
