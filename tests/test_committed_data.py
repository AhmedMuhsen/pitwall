"""The files a fresh clone (and the Docker image) rely on: data/processed/ is committed, so the app can run
without fetching anything. Loose bounds, so rebuilding the dataset doesn't break this."""
from pathlib import Path

import pytest

from pitwall.comparison import (TRAIN_YEARS, comparable_races, compare_driver, driver_choices, fit_inputs,
                                load_dataset, load_driver_names)
from pitwall.neutralisation import load_neutralisations

PROCESSED = Path(__file__).parent.parent / "data" / "processed"


@pytest.fixture(scope="module")
def deployed():
    rows = load_dataset(PROCESSED / "lap_dataset.parquet")
    windows = load_neutralisations(PROCESSED / "neutralisations.json")
    return rows, windows, fit_inputs(rows, TRAIN_YEARS, windows)


def test_the_three_files_the_app_needs_are_there():
    for name in ("lap_dataset.parquet", "driver_names.json", "neutralisations.json", "calibration.json"):
        assert (PROCESSED / name).stat().st_size > 1000, f"{name} is missing or empty: a fresh clone couldn't run the app"


def test_the_committed_data_covers_the_corpus(deployed):
    rows, windows, inputs = deployed

    assert len({r["session_key"] for r in rows}) >= 40
    assert {2023, 2024, 2025} <= {r["year"] for r in rows}
    assert sum(1 for ws in windows.values() if ws) >= 20             # safety-car windows are there
    assert load_driver_names(PROCESSED / "driver_names.json")
    assert inputs["sc_pit_loss"] is not None and inputs["wear_range"] > 0


def test_the_app_path_runs_on_the_committed_data(deployed):
    rows, windows, inputs = deployed
    races = comparable_races(rows, windows, inputs)
    year, circuit = races[0]
    car = driver_choices(rows, circuit, year, inputs["model"], windows=windows)[0]

    result = compare_driver(rows, inputs, circuit, year, car, traffic=True)

    assert len(races) >= 40
    assert abs(result["model_error"]) < 120 and len(result["ranking"]) >= 5


def test_the_committed_calibration_has_every_interval_the_app_shows():
    from pitwall.conformal import load_calibration
    calibration = load_calibration(PROCESSED / "calibration.json")

    assert calibration["level"] == 0.8
    for target in ("lap", "race_total", "race_total_safety_car", "gap"):
        t = calibration["targets"][target]
        assert t["half_width"] > 0 and t["n_calibration"] >= 100
        assert 0 <= t["rolling"]["coverage"] <= 1 and 0 <= t["static"]["coverage"] <= 1
