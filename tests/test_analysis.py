from pitwall.analysis import average_lap_time_by_tyre_age
import pytest

def test_empty_lap_raises():
    with pytest.raises(ValueError):
        average_lap_time_by_tyre_age([])

def test_none_lap_duration_is_ignored():
    laps = [
        {"tyre_age": 1, "lap_duration": 90.0},
        {"tyre_age": 1, "lap_duration": None},
    ]
    assert average_lap_time_by_tyre_age(laps) == {1: 90.0}
    
def test_normal_case():
    laps = [
        {"tyre_age": 1, "lap_duration": 90.0},
        {"tyre_age": 1, "lap_duration": 92.0},
        {"tyre_age": 4, "lap_duration": 93.0},
        {"tyre_age": 4, "lap_duration": 95.0},
    ]
    assert average_lap_time_by_tyre_age(laps) == {1: 91.0, 4: 94.0}

def test_all_ages_none():
    laps = [
        {"tyre_age": 1, "lap_duration": None},
        {"tyre_age": 1, "lap_duration": None},
        {"tyre_age": 4, "lap_duration": 93.0},
        {"tyre_age": 4, "lap_duration": 95.0},
    ]
    assert average_lap_time_by_tyre_age(laps) == {4: 94.0}
