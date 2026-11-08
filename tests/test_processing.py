from pitwall.processing import add_stint_data
from pitwall.processing import exclusion_reasons
import pytest

STINTS = [
    {"driver_number": 1, "lap_start": 1, "lap_end": 2, "tyre_age_at_start": 0, "compound": "SOFT"},
    {"driver_number": 1, "lap_start": 3, "lap_end": 4, "tyre_age_at_start": 3, "compound": "MEDIUM"},
]

def test_tyre_age_for_each_lap():
    laps = [{"driver_number": 1, "lap_number": n} for n in range(1, 6)]
    result = add_stint_data(laps, STINTS)
    assert [lap["tyre_age"] for lap in result] == [0, 1, 3, 4, None]

def test_each_lap_multiple_drivers():
    stints = [
    {"driver_number": 1, "lap_start": 1, "lap_end": 3, "tyre_age_at_start": 0, "compound": "SOFT"},
    {"driver_number": 44, "lap_start": 1, "lap_end": 3, "tyre_age_at_start": 2, "compound": "MEDIUM"},
    ]
    laps = [
        {"driver_number": 1, "lap_number": 2},
        {"driver_number": 44, "lap_number": 2},
    ]
    result = add_stint_data(laps, stints)
    assert [lap["tyre_age"] for lap in result] == [1, 3]

def test_check_number_of_laps():
    # checking number of laps going in is the same going out, including the unmatched laps, i.e. the ones that don't have a stint
    laps = [{"driver_number": 1, "lap_number": n} for n in range(1, 6)]
    result = add_stint_data(laps, STINTS)
    assert len(laps) == len(result)

def test_nonexistent_driver():
    laps = [{"driver_number": 99, "lap_number": 1}]
    result = add_stint_data(laps, STINTS)
    assert [lap["tyre_age"] for lap in result] == [None]

def test_multiple_stints_for_same_driver():
    stints = [
    {"driver_number": 1, "lap_start": 1, "lap_end": 3, "tyre_age_at_start": 0, "compound": "SOFT"},
    {"driver_number": 1, "lap_start": 3, "lap_end": 5, "tyre_age_at_start": 3, "compound": "MEDIUM"},
    ]
    laps = [{"driver_number": 1, "lap_number": n} for n in range(1, 6)]
    with pytest.raises(ValueError):
        add_stint_data(laps, stints)

def test_compound_for_each_lap():
    laps = [{"driver_number": 1, "lap_number": n} for n in range(1, 6)]
    result = add_stint_data(laps, STINTS)
    assert [lap["compound"] for lap in result] == ["SOFT", "SOFT", "MEDIUM", "MEDIUM", None]

def test_lap_1():
    lap = {'driver_number': 1, 'lap_number': 1, 'is_pit_out_lap': False, 'lap_duration': 98.2}
    reasons = exclusion_reasons(lap, STINTS, [lap])
    assert reasons == ['lap_1']

def test_pit_out():
    lap = {'driver_number': 1, 'lap_number': 3, 'is_pit_out_lap': True, 'lap_duration': 102.4}
    reasons = exclusion_reasons(lap, STINTS, [lap])
    assert reasons == ['pit_out']

def test_lap_1_pit_out():
    lap = {'driver_number': 1, 'lap_number': 1, 'is_pit_out_lap': True, 'lap_duration': 107.3}
    reasons = exclusion_reasons(lap, STINTS, [lap])
    assert reasons == ['lap_1', 'pit_out']

def test_clean():
    lap = {'driver_number': 1, 'lap_number': 3, 'is_pit_out_lap': False, 'lap_duration': 101.2}
    reasons = exclusion_reasons(lap, STINTS, [lap])
    assert reasons == []

def test_empty_lap_duration():
    lap = {'driver_number': 1, 'lap_number': 3, 'is_pit_out_lap': False, 'lap_duration': None}
    reasons = exclusion_reasons(lap, STINTS, [lap])
    assert reasons == ['null_lap_duration']

def test_in_lap():
    lap = {'driver_number': 1, 'lap_number': 2, 'is_pit_out_lap': False, 'lap_duration': 104.0}
    reasons = exclusion_reasons(lap, STINTS, [lap])
    assert reasons == ['in_lap']

def test_last_lap_of_race_is_clean():
    lap = {'driver_number': 1, 'lap_number': 4, 'is_pit_out_lap': False, 'lap_duration': 101.2}
    reasons = exclusion_reasons(lap, STINTS, [lap])
    assert reasons == []

def test_before_retirement():
    lap = {'driver_number': 1, 'lap_number': 4, 'is_pit_out_lap': False, 'lap_duration': 110.5}
    next_lap = {'driver_number': 1, 'lap_number': 5, 'is_pit_out_lap': False, 'lap_duration': None}
    reasons = exclusion_reasons(lap, STINTS, [lap, next_lap])
    assert reasons == ['before_retirement']

def test_other_drivers_next_lap_is_ignored():
    lap = {'driver_number': 1, 'lap_number': 4, 'is_pit_out_lap': False, 'lap_duration': 101.2}
    other = {'driver_number': 44, 'lap_number': 5, 'is_pit_out_lap': False, 'lap_duration': 101.2}
    reasons = exclusion_reasons(lap, STINTS, [lap, other])
    assert reasons == []

def test_lap_with_no_stint():
    lap = {'driver_number': 1, 'lap_number': 5, 'is_pit_out_lap': False, 'lap_duration': None}
    reasons = exclusion_reasons(lap, STINTS, [lap])
    assert reasons == ['null_lap_duration', 'no_stint']