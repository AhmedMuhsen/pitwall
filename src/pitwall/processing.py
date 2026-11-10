def find_stint(stints: list[dict], driver_number: int, lap_number: int) -> dict | None:
    '''
    Finds the stint for a given driver and lap number.
    Returns the stint if it exists, otherwise returns None.
    Raises a ValueError if multiple stints are found for the same driver and lap number.
    '''
    matches = []
    for stint in stints:
        if stint['driver_number'] == driver_number and stint['lap_start'] <= lap_number <= stint['lap_end']:
            matches.append(stint)
    if len(matches) == 0:
        return None
    elif len(matches) == 1:
        return matches[0]
    else:
        raise ValueError(f"Multiple stints found for driver {driver_number} at lap {lap_number}")

def add_stint_data(laps: list[dict], stints: list[dict]) -> list[dict]:
    '''
    Adds the tyre age, compound & stint number to the laps.
    Laps with no matching stint are kept with tyre_age, compound & stint_number set to None.
    Laps with multiple matching stints raise a ValueError.
    Returns the laps with the tyre age added.
    '''
    result = []
    for lap in laps:
        stint = find_stint(stints, lap['driver_number'], lap['lap_number'])
        if stint is None:
            result.append({**lap, "tyre_age": None, "compound": None, "stint_number": None})
        else:
            result.append({**lap, "tyre_age":stint['tyre_age_at_start'] + lap['lap_number'] - stint['lap_start'], "compound": stint['compound'], "stint_number": stint['stint_number']})
    return result

def has_lap(laps: list[dict], driver_number: int, lap_number: int) -> bool:
    '''
    Returns True if the driver has a lap with this lap number.
    '''
    for lap in laps:
        if lap['driver_number'] == driver_number and lap['lap_number'] == lap_number:
            return True
    return False

def find_safety_car_disruption_laps(race_control: list[dict]) -> set:
    '''
    Takes in race_control as a list of dicts.
    Returns the laps affected by the safety car (with a buffer of 1 lap before and 1 after) as a set.
    '''

    affected_laps = set()
    start_lap = None
    for r in race_control:
        if r['category'] == 'SafetyCar' and 'deployed' in r['message'].lower():
            start_lap = r['lap_number']
        if r['category'] == 'SafetyCar' and ('in this lap' in r['message'].lower() or 'ending' in r['message'].lower()):
            end_lap = r['lap_number']
            if start_lap is None:
                raise ValueError(f"Safety car ended on lap {end_lap} but was never deployed")
            for i in range(start_lap - 1, end_lap + 2):
                affected_laps.add(i)
            start_lap = None
    if start_lap is not None:
        raise ValueError(f'Safety car on {start_lap} has no end message')
    return affected_laps

def exclusion_reasons(lap: dict, stints: list[dict], laps: list[dict], safety_car_laps: set) -> list[str]:
    '''
    Returns every reason to exclude one lap, or an empty list if the lap is clean.
    Takes the lap, plus the stints and laps of its race and the safety car affected laps.
    Laps with no matching stint can't be in_lap or before_retirement.
    '''
    reasons = []
    if lap["lap_number"] == 1:
        reasons.append('lap_1')
    if lap["is_pit_out_lap"]:
        reasons.append('pit_out')
    if lap['lap_duration'] is None:
        reasons.append('null_lap_duration')
    if lap['lap_number'] in safety_car_laps:
        reasons.append('safety_car')
    stint = find_stint(stints, lap['driver_number'], lap['lap_number'])
    if stint is None:
        reasons.append('no_stint')
        return reasons
    if lap['lap_number'] == stint['lap_end']:
        next_lap_number = lap['lap_number'] + 1
        if find_stint(stints, lap['driver_number'], next_lap_number) is not None:
            reasons.append('in_lap')
        elif has_lap(laps, lap['driver_number'], next_lap_number):
            reasons.append('before_retirement')
    return reasons

def add_exclusion_reasons(laps: list[dict], stints: list[dict], race_control: list[dict]) -> list[dict]:
    '''
    Adds the exclusion reasons for each lap.
    Returns the laps with the exclusion reasons added.
    '''
    result = []
    affected_laps = find_safety_car_disruption_laps(race_control)
    for lap in laps:
        reasons = exclusion_reasons(lap, stints, laps, affected_laps)
        result.append({**lap, 'exclusion_reasons': reasons})
    return result

def is_racing_lap(reasons: list) -> bool:
    '''
    Takes list of reasons as input, returns True/False based on if a lap is considered a racing lap or not.

    '''
    for reason in reasons:
        if reason in ['safety_car', 'null_lap_duration', 'no_stint', 'in_lap', 'pit_out']:
            return False
    return True

def is_clean_lap(reasons:list) -> bool:
    return len(reasons) == 0

def build_race_rows(laps: list[dict], stints: list[dict], race_control: list[dict], circuit, year):
    stint_data = add_stint_data(laps, stints)
    labelled = add_exclusion_reasons(stint_data, stints, race_control)
    rows = []
    for lap in labelled:
        reasons = lap['exclusion_reasons']
        racing_lap = is_racing_lap(reasons)
        clean_lap = is_clean_lap(reasons)
        data = {**lap, 'circuit': circuit, 'year': year, 'is_clean': clean_lap, 'is_racing': racing_lap}
        rows.append(data)

    return rows

DATASET_COLUMNS = [
    'session_key', 'meeting_key', 'driver_number', 'lap_number', 'date_start',
    'lap_duration', 'is_pit_out_lap', 'stint_number', 'tyre_age', 'compound',
    'circuit', 'year', 'exclusion_reasons', 'is_clean', 'is_racing',
]

def keep_dataset_columns(rows: list[dict]) -> list[dict]:
    '''
    Takes rows from build_race_rows.
    Returns new rows with only DATASET_COLUMNS, in that order.
    Raises a KeyError if a row is missing one of them.
    '''
    result = []
    for row in rows:
        result.append({column: row[column] for column in DATASET_COLUMNS})
    return result