"""Model inputs and target built from the processed lap dataset rows."""
from collections import defaultdict
from statistics import median
import pandas as pd

def driver_reference_laps(rows: list[dict]) -> dict[tuple, float]:
    '''
    Each driver's median clean lap time in each race (the delta reference).

    rows: list of dicts (dataset rows), each with "session_key" (int),
        "driver_number" (int), "lap_duration" (float seconds) and
        "is_clean" (bool)

    returns: dict mapping (session_key, driver_number) -> median
        lap_duration in seconds, taken across that driver's clean laps
        in that race

    raises ValueError if rows is empty. Only clean laps are used, so laps
    with no time (never clean) are left out. A driver with no clean laps
    in a race has no key, never 0.
    '''
    if not rows:
        raise ValueError("Laps list is empty")
    
    grouped = defaultdict(list)
    for lap in rows:
        if lap['is_clean']:
            grouped[(lap['session_key'], lap['driver_number'])].append(lap['lap_duration'])
        
    median_duration_by_driver =  {(session_key, driver_number) : median(durations) for (session_key, driver_number), durations in grouped.items()}

    return median_duration_by_driver
        
def add_delta(rows: list[dict], references: dict[tuple, float]) -> list[dict]:
    result = []
    for row in rows:
        key = (row['session_key'], row['driver_number'])
        ref = references.get(key)
        if ref is None or row['lap_duration'] is None:
            delta = None
        else:
            delta = row['lap_duration'] - ref
        result.append({**row, "delta": delta})
    return result

def pair_age_columns(df: pd.DataFrame, pairs: list[str]) -> pd.DataFrame:
    pair = df['compound'] + '@' + df['circuit']

    unknown = pair[~pair.isin(pairs)]
    if not unknown.empty:
        raise ValueError(f"Pairs not seen in training: {sorted(set(unknown))}")
    columns = {}
    for p in pairs:
        columns["age:" + p] = (pair == p) * df['tyre_age']
    return pd.DataFrame(columns, index = df.index)