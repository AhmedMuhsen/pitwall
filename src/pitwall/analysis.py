from collections import defaultdict
from unittest import result

def average_lap_time_by_tyre_age(laps):
    """Average lap time at each tyre age.

    laps: list of dicts, each with "tyre_age" (int, laps on the set)
        and "lap_duration" (float seconds, or None if not timed)
        
    returns: dict mapping tyre_age -> mean lap_duration in seconds

    raises ValueError if laps is empty. Laps with lap_duration None are
    ignored; a tyre age with no timed laps is absent from the result.
    """
    if not laps:
        raise ValueError("Laps list is empty")
    grouped = defaultdict(list)
    for lap in laps:
        if lap['lap_duration'] is not None:
            grouped[lap['tyre_age']].append(lap['lap_duration'])
        
    mean_lap_by_age = {age : sum(durations) / len(durations) for age, durations in grouped.items()}
    return mean_lap_by_age

def max_clean_tyre_age(rows: list[dict]) -> dict:
    '''
    Takes in the race rows
    Returns the maximum tyre age of a clean lap, grouped by the circuit, year, and compound
    Circuit, year, compound with no clean laps have no key.
    '''
    result = {}
    for lap in rows:
        key = (lap['circuit'], lap['year'], lap['compound'])
        if lap['is_clean']:
            if key not in result:
                result[key] = lap['tyre_age']

            elif lap['tyre_age'] > result[key]:
                result[key] = lap['tyre_age']
            
    return result
        