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