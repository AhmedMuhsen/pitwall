import pytest

from pitwall.features import driver_reference_laps
from pitwall.features import add_delta, add_race_fraction, pair_age_columns
import pandas as pd
import pytest

def test_median_calculation():
    rows = [
        {'session_key' : 1, 'driver_number' : 44, 'lap_duration': 84.3, 'is_clean': True},
        {'session_key' : 1, 'driver_number' : 44, 'lap_duration': 85.3, 'is_clean': True},
        {'session_key' : 1, 'driver_number' : 44, 'lap_duration': 82.1, 'is_clean': True},
        {'session_key' : 1, 'driver_number' : 44, 'lap_duration': 81.7, 'is_clean': True},
        {'session_key' : 1, 'driver_number' : 16, 'lap_duration': 84.8, 'is_clean': True},
        {'session_key' : 1, 'driver_number' : 16, 'lap_duration': 81.2, 'is_clean': True},
        {'session_key' : 1, 'driver_number' : 16, 'lap_duration': 82.4, 'is_clean': True},
        {'session_key' : 1, 'driver_number' : 16, 'lap_duration': 82.7, 'is_clean': True},
        {'session_key' : 1, 'driver_number' : 16, 'lap_duration': 83.1, 'is_clean': True},
        {'session_key' : 1, 'driver_number' : 16, 'lap_duration': 120.0, 'is_clean': False},
    ]
    result = driver_reference_laps(rows)
    
    assert result == pytest.approx({(1, 44): 83.2, (1, 16): 82.7})

def test_unclean_laps_calculation():
    rows = [
        {'session_key' : 1, 'driver_number' : 44, 'lap_duration': 84.3, 'is_clean': False},
        {'session_key' : 1, 'driver_number' : 44, 'lap_duration': 85.3, 'is_clean': False},
        {'session_key' : 1, 'driver_number' : 44, 'lap_duration': 82.1, 'is_clean': False},
        {'session_key' : 1, 'driver_number' : 44, 'lap_duration': 81.7, 'is_clean': False},
        {'session_key' : 1, 'driver_number' : 16, 'lap_duration': 84.8, 'is_clean': True},
        {'session_key' : 1, 'driver_number' : 16, 'lap_duration': 81.2, 'is_clean': True},
        {'session_key' : 1, 'driver_number' : 16, 'lap_duration': 82.4, 'is_clean': True},
        {'session_key' : 1, 'driver_number' : 16, 'lap_duration': 82.7, 'is_clean': True},
        {'session_key' : 1, 'driver_number' : 16, 'lap_duration': 83.1, 'is_clean': True},
        {'session_key' : 1, 'driver_number' : 16, 'lap_duration': 120.0, 'is_clean': False},
    ]
    result = driver_reference_laps(rows)
    
    assert result == pytest.approx({(1, 16): 82.7})

def test_add_delta():
    rows = [
        {'session_key' : 1, 'driver_number' : 44, 'lap_duration': 81.5},
        {'session_key' : 1, 'driver_number' : 16, 'lap_duration': 82.0},
        {'session_key' : 1, 'driver_number' : 44, 'lap_duration': None},
    ]
    references = {(1, 44): 80.0}

    result = add_delta(rows, references)

    assert len(result) == 3
    assert result[0]['delta'] == pytest.approx(1.5)
    assert result[1]['delta'] is None
    assert result[2]['delta'] is None

def test_add_delta_keeps_original_rows():
    rows = [{'session_key' : 1, 'driver_number' : 44, 'lap_duration': 81.5}]

    result = add_delta(rows, {(1, 44): 80.0})

    assert 'delta' not in rows[0]
    assert result[0]['lap_duration'] == 81.5

def test_pair_age_columns_puts_age_in_matching_pair_only():
    df = pd.DataFrame({
        "compound" : ["SOFT", "HARD", "SOFT"],
        "circuit": ["Sakhir", "Monza", "Sakhir"],
        "tyre_age": [8, 15, 2]
    })
    result = pair_age_columns(df, ['HARD@Monza', "SOFT@Sakhir"])
    expected = pd.DataFrame({
        "age:HARD@Monza": [0, 15, 0],
        "age:SOFT@Sakhir": [8, 0, 2],
    })

    pd.testing.assert_frame_equal(result, expected)

def test_pair_age_columns_raises_on_unseen_pair():
    df = pd.DataFrame({"compound": ["MEDIUM"], "circuit": ["Sakhir"], "tyre_age": [5]})
    with pytest.raises(ValueError, match="MEDIUM@Sakhir"):
        pair_age_columns(df, ["HARD@Monza", "SOFT@Sakhir"])

def test_add_race_fraction_uses_each_race_length():
    rows = [
        {"session_key": 1, "lap_number": 1},
        {"session_key": 1, "lap_number": 4},
        {"session_key": 2, "lap_number": 1},
        {"session_key": 2, "lap_number": 2},
    ]
    result = add_race_fraction(rows)

    assert [row["race_fraction"] for row in result] == pytest.approx([0.25, 1.0, 0.5, 1.0])


def test_add_race_fraction_empty_rows():
    with pytest.raises(ValueError):
        add_race_fraction([])
