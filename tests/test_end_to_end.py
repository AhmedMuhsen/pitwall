"""The whole chain on a small real subset (Monza and Hungaroring, 2023-2025; tests/fixtures/mini_laps.parquet):
parquet -> rows -> model and pit loss -> per-car comparison -> verdict."""
import math
from pathlib import Path

import pytest

from pitwall.comparison import (comparable_races, compare_driver, custom_strategy, driver_choices,
                                fit_inputs, gap_ranges, load_dataset, verdict)
from pitwall.neutralisation import load_neutralisations

FIXTURE = Path(__file__).parent / "fixtures" / "mini_laps.parquet"
REAL = "actual"      # compare_driver measures every gap against the car's real strategy


@pytest.fixture(scope="module")
def data():
    rows = load_dataset(FIXTURE)
    return rows, fit_inputs(rows, [2023, 2024])


def test_inputs_cover_both_circuits(data):
    _, inputs = data

    assert sorted(inputs["pit_loss"]) == ["Hungaroring", "Monza"]
    assert all(15 < v["median"] < 35 for v in inputs["pit_loss"].values())   # seconds per stop
    assert 0 < inputs["wear_range"] < 0.1
    assert len(inputs["held_out_wear_errors"]) > 4


def test_every_comparable_car_can_be_compared(data):
    rows, inputs = data
    assert (2025, "Monza") in comparable_races(rows)      # out-of-sample races are included

    for year, circuit in comparable_races(rows):
        cars = driver_choices(rows, circuit, year, inputs["model"])
        assert len(cars) >= 5
        result = compare_driver(rows, inputs, circuit, year, cars[0])
        assert math.isfinite(result["simulated_actual"]) and result["actual_time"] > 3000
        assert abs(result["model_error"]) < 120            # a broken chain would be off by minutes
        assert {r["strategy"] for r in result["ranking"]} >= {REAL, "1stop_MH_late", "2stop_MHH"}
        assert next(r for r in result["ranking"] if r["strategy"] == REAL)["gap"] == 0


def test_verdict_and_custom_strategy_on_real_rows(data):
    rows, inputs = data
    car = driver_choices(rows, "Monza", 2024, inputs["model"])[0]
    race_laps = max(r["lap_number"] for r in rows if r["circuit"] == "Monza" and r["year"] == 2024
                    and r["lap_duration"] is not None)
    custom = custom_strategy(["MEDIUM", "HARD"], [race_laps // 2], race_laps)

    result = compare_driver(rows, inputs, "Monza", 2024, car, custom=custom)
    answer = verdict(gap_ranges(result["sensitivity"], REAL))

    assert "custom" in result["strategies"]
    assert answer["kind"] in {"agrees", "too_close", "leans", "prefers"}


def test_invalid_input_is_refused_not_simulated(data):
    rows, inputs = data
    car = driver_choices(rows, "Monza", 2024, inputs["model"])[0]

    with pytest.raises(ValueError, match="No race"):
        compare_driver(rows, inputs, "Nowhere", 2024, car)
    with pytest.raises(ValueError, match="didn't run every lap"):
        compare_driver(rows, inputs, "Monza", 2024, 9999)
    with pytest.raises(ValueError, match="two different dry compounds"):
        compare_driver(rows, inputs, "Monza", 2024, car, custom={"compounds": ["HARD", "HARD"], "pit_laps": [20]})


def test_traffic_changes_the_numbers_but_not_the_shape(data):
    rows, inputs = data
    car = driver_choices(rows, "Monza", 2024, inputs["model"])[0]

    off = compare_driver(rows, inputs, "Monza", 2024, car)
    on = compare_driver(rows, inputs, "Monza", 2024, car, traffic=True)

    assert {r["strategy"] for r in on["ranking"]} == {r["strategy"] for r in off["ranking"]}
    assert math.isfinite(on["simulated_actual"]) and on["simulated_actual"] != off["simulated_actual"]
    assert abs(on["model_error"]) < 120
    assert len(on["sensitivity"]) == len(off["sensitivity"])
    assert inputs["traffic_table"]["mean"][0] > inputs["traffic_table"]["mean"][-1]    # close behind costs time


@pytest.fixture(scope="module")
def safety_car_data():
    rows = load_dataset(FIXTURE.parent / "mini_safety_car_laps.parquet")
    windows = load_neutralisations(FIXTURE.parent / "mini_neutralisations.json")
    return rows, windows, fit_inputs(rows, [2023, 2024], windows)


def test_safety_car_races_become_comparable_with_their_windows(safety_car_data):
    rows, windows, inputs = safety_car_data

    assert (2025, "Sakhir") not in comparable_races(rows)                   # a real safety car, no windows given
    assert (2025, "Sakhir") in comparable_races(rows, windows)
    ratio = inputs["sc_pit_loss"]
    assert ratio["n"] >= 10 and 0.4 < ratio["ratio"] < 1.0                     # stops under a real safety car are cheaper


def test_comparing_a_car_in_a_safety_car_race(safety_car_data):
    rows, windows, inputs = safety_car_data
    car = driver_choices(rows, "Sakhir", 2025, inputs["model"], windows=windows)[0]

    result = compare_driver(rows, inputs, "Sakhir", 2025, car, traffic=True)

    assert result["neutralisation_windows"] == [{"kind": "SC", "start": 32, "end": 35}]    # Sakhir 2025
    assert result["strategies"]["1stop_under_SC"]["pit_laps"] == [33]                       # first lap after deployment
    assert math.isfinite(result["simulated_actual"]) and abs(result["model_error"]) < 90
    with pytest.raises(ValueError, match="no safety-car windows"):
        compare_driver(rows, {**inputs, "neutralisations": {}}, "Sakhir", 2025, car)


def test_refit_ensemble_is_repeatable_and_keeps_every_pair(data):
    rows, _ = data
    first = fit_inputs(rows, [2023, 2024], refits=4)
    second = fit_inputs(rows, [2023, 2024], refits=4)

    assert len(first["ensemble"]) == 4
    assert [m["pit_loss"]["Monza"]["median"] for m in first["ensemble"]] == \
           [m["pit_loss"]["Monza"]["median"] for m in second["ensemble"]]          # fixed seed
    full_pairs = set(first["model"].pair_adjustments())
    assert all(set(m["model"].pair_adjustments()) == full_pairs for m in first["ensemble"])
    # Different subsets give (slightly) different fits.
    assert len({round(m["traffic_table"]["mean"][0], 6) for m in first["ensemble"]}) > 1
    assert "ensemble" not in first["ensemble"][0]


def test_compare_driver_reports_the_gap_under_every_refit(data):
    rows, _ = data
    inputs = fit_inputs(rows, [2023, 2024], refits=4)
    car = driver_choices(rows, "Monza", 2024, inputs["model"])[0]

    result = compare_driver(rows, inputs, "Monza", 2024, car, traffic=True)

    assert set(result["refit_gaps"]) == set(result["strategies"])
    assert all(len(gaps) == 4 for gaps in result["refit_gaps"].values())
    assert all(g == 0 for g in result["refit_gaps"]["actual"])                     # the baseline against itself
    ranges = gap_ranges(result["sensitivity"], "actual", refit_gaps=result["refit_gaps"])
    assert all(r["refits"] == 4 and 0 <= r["p_faster"] <= 1 for r in ranges)
    assert verdict(ranges)["kind"] in {"agrees", "too_close", "leans", "prefers"}
