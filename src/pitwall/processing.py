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
    Adds the tyre age & compound to the laps.
    Laps with no matching stint are kept with tyre_age & compound set to None.
    Laps with multiple matching stints raise a ValueError.
    Returns the laps with the tyre age added.
    '''
    result = []
    for lap in laps:
        stint = find_stint(stints, lap['driver_number'], lap['lap_number'])
        if stint is None:
            result.append({**lap, "tyre_age": None, "compound": None})
        else:
            result.append({**lap, "tyre_age":stint['tyre_age_at_start'] + lap['lap_number'] - stint['lap_start'], "compound": stint['compound']})
    return result

def has_lap(laps: list[dict], driver_number: int, lap_number: int) -> bool:
    '''
    Returns True if the driver has a lap with this lap number.
    '''
    for lap in laps:
        if lap['driver_number'] == driver_number and lap['lap_number'] == lap_number:
            return True
    return False

def exclusion_reasons(lap: dict, stints: list[dict], laps: list[dict]) -> list[str]:
    '''
    Returns every reason to exclude one lap, or an empty list if the lap is clean.
    Takes the lap, plus the stints and laps of its race.
    Laps with no matching stint can't be in_lap or before_retirement.
    '''
    reasons = []
    if lap["lap_number"] == 1:
        reasons.append('lap_1')
    if lap["is_pit_out_lap"]:
        reasons.append('pit_out')
    if lap['lap_duration'] is None:
        reasons.append('null_lap_duration')
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