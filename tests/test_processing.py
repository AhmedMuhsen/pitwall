from pitwall.processing import add_stint_data
from pitwall.processing import exclusion_reasons
from pitwall.processing import find_safety_car_disruption_laps
from pitwall.processing import add_exclusion_reasons
from pitwall.processing import is_racing_lap
from pitwall.processing import build_race_rows
from pitwall.processing import keep_dataset_columns, DATASET_COLUMNS
import pytest

STINTS = [
    {"driver_number": 1, "stint_number": 1, "lap_start": 1, "lap_end": 2, "tyre_age_at_start": 0, "compound": "SOFT"},
    {"driver_number": 1, "stint_number": 2, "lap_start": 3, "lap_end": 4, "tyre_age_at_start": 3, "compound": "MEDIUM"},
]
RACE_LAPS = [
    {"driver_number": 1, "lap_number": 1, 'is_pit_out_lap': False, 'lap_duration': 101.2},
    {"driver_number": 1, "lap_number": 2, 'is_pit_out_lap': False, 'lap_duration': 101.2},
    {"driver_number": 1, "lap_number": 3, 'is_pit_out_lap': True, 'lap_duration': 101.2},
    {"driver_number": 1, "lap_number": 4, 'is_pit_out_lap': False, 'lap_duration': 101.2}
]

def test_tyre_age_for_each_lap():
    laps = [{"driver_number": 1, "lap_number": n} for n in range(1, 6)]
    result = add_stint_data(laps, STINTS)
    assert [lap["tyre_age"] for lap in result] == [0, 1, 3, 4, None]

def test_each_lap_multiple_drivers():
    stints = [
    {"driver_number": 1, "stint_number": 1, "lap_start": 1, "lap_end": 3, "tyre_age_at_start": 0, "compound": "SOFT"},
    {"driver_number": 44, "stint_number": 1, "lap_start": 1, "lap_end": 3, "tyre_age_at_start": 2, "compound": "MEDIUM"},
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
    {"driver_number": 1, "stint_number": 1, "lap_start": 1, "lap_end": 3, "tyre_age_at_start": 0, "compound": "SOFT"},
    {"driver_number": 1, "stint_number": 2, "lap_start": 3, "lap_end": 5, "tyre_age_at_start": 3, "compound": "MEDIUM"},
    ]
    laps = [{"driver_number": 1, "lap_number": n} for n in range(1, 6)]
    with pytest.raises(ValueError):
        add_stint_data(laps, stints)

def test_compound_for_each_lap():
    laps = [{"driver_number": 1, "lap_number": n} for n in range(1, 6)]
    result = add_stint_data(laps, STINTS)
    assert [lap["compound"] for lap in result] == ["SOFT", "SOFT", "MEDIUM", "MEDIUM", None]

def test_stint_number_for_each_lap():
    laps = [{"driver_number": 1, "lap_number": n} for n in range(1, 6)]
    result = add_stint_data(laps, STINTS)
    assert [lap["stint_number"] for lap in result] == [1, 1, 2, 2, None]

def test_lap_1():
    lap = {'driver_number': 1, 'lap_number': 1, 'is_pit_out_lap': False, 'lap_duration': 98.2}
    reasons = exclusion_reasons(lap, STINTS, [lap], set())
    assert reasons == ['lap_1']

def test_pit_out():
    lap = {'driver_number': 1, 'lap_number': 3, 'is_pit_out_lap': True, 'lap_duration': 102.4}
    reasons = exclusion_reasons(lap, STINTS, [lap], set())
    assert reasons == ['pit_out']

def test_lap_1_pit_out():
    lap = {'driver_number': 1, 'lap_number': 1, 'is_pit_out_lap': True, 'lap_duration': 107.3}
    reasons = exclusion_reasons(lap, STINTS, [lap], set())
    assert reasons == ['lap_1', 'pit_out']

def test_clean():
    lap = {'driver_number': 1, 'lap_number': 3, 'is_pit_out_lap': False, 'lap_duration': 101.2}
    reasons = exclusion_reasons(lap, STINTS, [lap], set())
    assert reasons == []

def test_empty_lap_duration():
    lap = {'driver_number': 1, 'lap_number': 3, 'is_pit_out_lap': False, 'lap_duration': None}
    reasons = exclusion_reasons(lap, STINTS, [lap], set())
    assert reasons == ['null_lap_duration']

def test_in_lap():
    lap = {'driver_number': 1, 'lap_number': 2, 'is_pit_out_lap': False, 'lap_duration': 104.0}
    reasons = exclusion_reasons(lap, STINTS, [lap], set())
    assert reasons == ['in_lap']

def test_last_lap_of_race_is_clean():
    lap = {'driver_number': 1, 'lap_number': 4, 'is_pit_out_lap': False, 'lap_duration': 101.2}
    reasons = exclusion_reasons(lap, STINTS, [lap], set())
    assert reasons == []

def test_before_retirement():
    lap = {'driver_number': 1, 'lap_number': 4, 'is_pit_out_lap': False, 'lap_duration': 110.5}
    next_lap = {'driver_number': 1, 'lap_number': 5, 'is_pit_out_lap': False, 'lap_duration': None}
    reasons = exclusion_reasons(lap, STINTS, [lap, next_lap], set())
    assert reasons == ['before_retirement']

def test_other_drivers_next_lap_is_ignored():
    lap = {'driver_number': 1, 'lap_number': 4, 'is_pit_out_lap': False, 'lap_duration': 101.2}
    other = {'driver_number': 44, 'lap_number': 5, 'is_pit_out_lap': False, 'lap_duration': 101.2}
    reasons = exclusion_reasons(lap, STINTS, [lap, other], set())
    assert reasons == []

def test_lap_with_no_stint():
    lap = {'driver_number': 1, 'lap_number': 5, 'is_pit_out_lap': False, 'lap_duration': None}
    reasons = exclusion_reasons(lap, STINTS, [lap], set())
    assert reasons == ['null_lap_duration', 'no_stint']

def test_lap_with_lap_duration_no_stint():
    lap = {'driver_number': 1, 'lap_number': 5, 'is_pit_out_lap': False, 'lap_duration': 124.2}
    reasons = exclusion_reasons(lap, STINTS, [lap], set())
    assert reasons == ['no_stint']

def test_two_safety_cars():
    race_control = [{'category': 'SafetyCar', 'lap_number': 5, 'message': 'SAFETY CAR DEPLOYED'},
                    {'category': 'SafetyCar', 'lap_number': 6, 'message': 'SAFETY CAR IN THIS LAP'},
                    {'category': 'SafetyCar', 'lap_number': 20, 'message': 'SAFETY CAR DEPLOYED'},
                    {'category': 'SafetyCar', 'lap_number': 22, 'message': 'SAFETY CAR IN THIS LAP'}]
    result = find_safety_car_disruption_laps(race_control)
    assert result == {4, 5, 6, 7, 19, 20, 21, 22, 23}

def test_safety_car_never_ends():
    race_control = [{'category': 'SafetyCar', 'lap_number': 5, 'message': 'SAFETY CAR DEPLOYED'},]
    with pytest.raises(ValueError):
        find_safety_car_disruption_laps(race_control)

def test_not_a_safety_car():
    race_control = [{'category': 'Flag', 'lap_number': 5, 'message': 'GREEN LIGHT - PIT EXIT OPEN'},]
    result = find_safety_car_disruption_laps(race_control)
    assert result == set()

def test_no_start_lap():
    race_control = [{'category': 'SafetyCar', 'lap_number': 6, 'message': 'SAFETY CAR IN THIS LAP'}]
    with pytest.raises(ValueError):
        find_safety_car_disruption_laps(race_control)

def test_safety_car():
    race_control = [{'category': 'SafetyCar', 'lap_number': 3, 'message': 'SAFETY CAR DEPLOYED'},
                    {'category': 'SafetyCar', 'lap_number': 6, 'message': 'SAFETY CAR IN THIS LAP'},
                    {'category': 'SafetyCar', 'lap_number': 20, 'message': 'SAFETY CAR DEPLOYED'},
                    {'category': 'SafetyCar', 'lap_number': 22, 'message': 'SAFETY CAR IN THIS LAP'}]
    lap = {'driver_number': 1, 'lap_number': 3, 'is_pit_out_lap': False, 'lap_duration': 101.2}
    affected_laps = find_safety_car_disruption_laps(race_control)
    reasons = exclusion_reasons(lap, STINTS, [lap], affected_laps)
    assert reasons == ['safety_car']

def test_no_safety_car():
    race_control = [{'category': 'SafetyCar', 'lap_number': 7, 'message': 'SAFETY CAR DEPLOYED'},
                    {'category': 'SafetyCar', 'lap_number': 8, 'message': 'SAFETY CAR IN THIS LAP'},
                    {'category': 'SafetyCar', 'lap_number': 20, 'message': 'SAFETY CAR DEPLOYED'},
                    {'category': 'SafetyCar', 'lap_number': 22, 'message': 'SAFETY CAR IN THIS LAP'}]
    lap = {'driver_number': 1, 'lap_number': 3, 'is_pit_out_lap': False, 'lap_duration': 101.2}
    affected_laps = find_safety_car_disruption_laps(race_control)
    reasons = exclusion_reasons(lap, STINTS, [lap], affected_laps)
    assert reasons == []


def test_lap_in_equals_out():
    result = add_exclusion_reasons(RACE_LAPS, STINTS, [])
    assert len(result) == len(RACE_LAPS)


def test_correct_reasons():
    race_control = [{'category': 'SafetyCar', 'lap_number': 4, 'message': 'SAFETY CAR DEPLOYED'},
                    {'category': 'SafetyCar', 'lap_number': 8, 'message': 'SAFETY CAR IN THIS LAP'},
                    {'category': 'SafetyCar', 'lap_number': 20, 'message': 'SAFETY CAR DEPLOYED'},
                    {'category': 'SafetyCar', 'lap_number': 22, 'message': 'SAFETY CAR IN THIS LAP'}]
    result = add_exclusion_reasons(RACE_LAPS, STINTS, race_control)
    assert result[0]['exclusion_reasons'] == ['lap_1']
    assert result[1]['exclusion_reasons'] == ['in_lap']
    assert result[2]['exclusion_reasons'] == ['pit_out', 'safety_car']
    assert result[3]['exclusion_reasons'] == ['safety_car']

def test_originals_untouched():
    race_control = [{'category': 'SafetyCar', 'lap_number': 4, 'message': 'SAFETY CAR DEPLOYED'},
                    {'category': 'SafetyCar', 'lap_number': 8, 'message': 'SAFETY CAR IN THIS LAP'},
                    {'category': 'SafetyCar', 'lap_number': 20, 'message': 'SAFETY CAR DEPLOYED'},
                    {'category': 'SafetyCar', 'lap_number': 22, 'message': 'SAFETY CAR IN THIS LAP'}]
    result = add_exclusion_reasons(RACE_LAPS, STINTS, race_control)
    assert 'exclusion_reasons' not in RACE_LAPS[0]

def test_invalid_race_lap():
    reasons = ['safety_car']
    result = is_racing_lap(reasons)
    assert result == False
    reasons = ['testing', 'in_lap']
    result = is_racing_lap(reasons)
    assert result == False

def test_valid_race_lap():
    reasons = []
    result = is_racing_lap(reasons)
    assert result == True
    
def test_lap_1_valid_race_lap():
    reasons = ['lap_1']
    result = is_racing_lap(reasons)
    assert result == True


def test_building_race_rows():
    rows = build_race_rows(RACE_LAPS, STINTS, [], 'Monza', 2024)
    assert len(rows) == len(RACE_LAPS)
    assert rows[0]['is_racing'] == True
    assert rows[0]['is_clean'] == False
    assert rows[0]['circuit'] == 'Monza'
    assert rows[0]['year'] == 2024
    assert rows[1]['is_racing'] == False
    assert rows[1]['is_clean'] == False
    assert rows[3]['is_racing'] == True
    assert rows[3]['is_clean'] == True

def test_keep_dataset_columns_drops_the_rest():
    row = {column: 1 for column in DATASET_COLUMNS}
    row['segments_sector_1'] = [2048, 2049]
    result = keep_dataset_columns([row])
    assert list(result[0].keys()) == DATASET_COLUMNS
    assert 'segments_sector_1' in row

def test_keep_dataset_columns_missing_column():
    row = {column: 1 for column in DATASET_COLUMNS}
    del row['tyre_age']
    with pytest.raises(KeyError):
        keep_dataset_columns([row])