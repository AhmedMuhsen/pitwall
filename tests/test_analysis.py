from pitwall.analysis import average_lap_time_by_tyre_age
from pitwall.analysis import max_clean_tyre_age
from pitwall.analysis import median_clean_lap_by_race_lap
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

def test_two_clean_laps():
    rows = [
        {"circuit": 'Monza', "year" : 2024, "compound" : 'SOFT', 'is_clean': True, 'tyre_age' : 7},
        {"circuit": 'Monza', "year" : 2024, "compound" : 'SOFT', 'is_clean': True, 'tyre_age' : 3}
    ]

    result = max_clean_tyre_age(rows)

    assert result == {("Monza", 2024, "SOFT"): 7}

def test_one_unclean_laps():
    rows = [
        {"circuit": 'Monza', "year" : 2024, "compound" : 'SOFT', 'is_clean': True, 'tyre_age' : 3},
        {"circuit": 'Monza', "year" : 2024, "compound" : 'SOFT', 'is_clean': False, 'tyre_age' : 12}
    ]

    result = max_clean_tyre_age(rows)
    assert result == {("Monza", 2024, "SOFT"): 3}

def test_invalid_unclean_laps():
    rows = [
        {"circuit": 'Monza', "year" : 2024, "compound" : 'SOFT', 'is_clean': False, 'tyre_age' : 3},

    ]

    result = max_clean_tyre_age(rows)
    assert ("Monza", 2024, "SOFT") not in result

def test_two_years():
    rows = [
        {"circuit": 'Monza', "year" : 2024, "compound" : 'SOFT', 'is_clean': True, 'tyre_age' : 3},
        {"circuit": 'Monza', "year" : 2025, "compound" : 'SOFT', 'is_clean': True, 'tyre_age' : 3},

    ]

    result = max_clean_tyre_age(rows)
    assert ("Monza", 2024, "SOFT") in result
    assert ("Monza", 2025, "SOFT") in result

def test_median_by_race_lap():
    rows = [
        {"session_key": 1, "lap_number": 1, "lap_duration": 80.0, "is_clean": True},
        {"session_key": 1, "lap_number": 1, "lap_duration": 81.0, "is_clean": True},
        {"session_key": 1, "lap_number": 1, "lap_duration": 99.0, "is_clean": False},
        {"session_key": 1, "lap_number": 2, "lap_duration": 79.0, "is_clean": True},
        {"session_key": 1, "lap_number": 2, "lap_duration": 79.5, "is_clean": True},
        {"session_key": 1, "lap_number": 2, "lap_duration": 85.0, "is_clean": True},
        {"session_key": 2, "lap_number": 1, "lap_duration": 50.0, "is_clean": True},
    ]

    result = median_clean_lap_by_race_lap(rows, 1)
    assert result == {1: 80.5, 2: 79.5}

def test_median_by_race_lap_no_clean_laps():
    rows = [
        {"session_key": 1, "lap_number": 1, "lap_duration": 80.0, "is_clean": False},
    ]

    assert median_clean_lap_by_race_lap(rows, 1) == {}

def test_median_by_race_lap_empty_raises():
    with pytest.raises(ValueError):
        median_clean_lap_by_race_lap([], 1)
