from collections import defaultdict
from statistics import median, quantiles

import pandas as pd

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

def median_clean_lap_by_race_lap(laps, session_key):
    """Median clean lap time at each race lap, for one race.

    laps: list of dicts (dataset rows), each with "session_key" (int),
        "lap_number" (int), "lap_duration" (float seconds) and
        "is_clean" (bool)
    session_key: the race to use; rows from other sessions are ignored

    returns: dict mapping lap_number -> median lap_duration in seconds,
        taken across the drivers whose lap was clean

    raises ValueError if laps is empty. Only clean laps are used, so laps
    with no time (never clean) are left out; a lap number with no clean
    laps is absent from the result, and a session with none returns {}.
    """
    if not laps:
        raise ValueError("Laps list is empty")
    grouped = defaultdict(list)
    for lap in laps:
        if lap['session_key'] == session_key and lap['is_clean']:
            grouped[lap['lap_number']].append(lap['lap_duration'])
        
    median_duration_by_lap =  {lap_number : median(durations) for lap_number, durations in grouped.items()}

    return median_duration_by_lap
        


def stop_losses(rows: list[dict], model) -> list[dict]:
    '''
    Time each pit stop cost beyond two normal racing laps (one pit-loss measurement per stop).

    rows: dataset rows with "session_key", "driver_number", "lap_number",
        "circuit", "year", "exclusion_reasons", "delta" (None if untimed or no
        reference) and the model's inputs ("compound", "tyre_age", "race_fraction")
    model: fitted model whose predict(DataFrame) returns delta in seconds, the
        same one the simulator uses

    returns: one dict per stop (a lap with the "in_lap" reason) with "circuit",
        "year", "session_key", "driver_number", "in_lap" (lap number), "loss"
        and "skip_reason". loss = (actual - predicted delta) on the in-lap plus
        the same on the out-lap (the next lap), in seconds: exactly what
        simulator.simulate leaves out when it predicts both as normal laps.
        A stop that can't be measured keeps its record with loss None and
        skip_reason "no_out_lap", "safety_car" (either lap) or "no_time"
        (either lap has no delta); measured stops have skip_reason None.
        Empty list if there are no stops.
    '''
    by_key = {(r["session_key"], r["driver_number"], r["lap_number"]): r for r in rows}
    stops = []
    measured = []  # (stop record, in-lap row, out-lap row)
    for row in rows:
        if "in_lap" not in row["exclusion_reasons"]:
            continue
        out = by_key.get((row["session_key"], row["driver_number"], row["lap_number"] + 1))
        record = {"circuit": row["circuit"], "year": row["year"], "session_key": row["session_key"],
                  "driver_number": row["driver_number"], "in_lap": row["lap_number"],
                  "loss": None, "skip_reason": None}
        if out is None:
            record["skip_reason"] = "no_out_lap"
        elif "safety_car" in row["exclusion_reasons"] or "safety_car" in out["exclusion_reasons"]:
            record["skip_reason"] = "safety_car"
        elif row["delta"] is None or out["delta"] is None:
            record["skip_reason"] = "no_time"
        else:
            measured.append((record, row, out))
        stops.append(record)

    if measured:
        # One predict call for all in-laps and out-laps, in pairs.
        laps = pd.DataFrame([lap for _, in_row, out_row in measured for lap in (in_row, out_row)])
        predicted = model.predict(laps)
        for i, (record, in_row, out_row) in enumerate(measured):
            record["loss"] = float((in_row["delta"] - predicted[2 * i]) + (out_row["delta"] - predicted[2 * i + 1]))
    return stops


def pit_loss_by_circuit(losses: list[dict], years: list[int]) -> dict[str, dict]:
    '''
    Pit loss per circuit from the stops in the given years (the simulator's pit_loss).

    losses: records from stop_losses, each with "circuit", "year", "loss"
        (seconds or None) and "skip_reason"
    years: the years to use (the model's training years)

    returns: dict circuit -> {"median": median loss, "q25" and "q75": 25th
        and 75th percentiles (the spread, for sensitivity tests), "measured":
        number of stops with a loss, "skipped": count per skip_reason}.
    The median keeps one slow stop or a penalty from moving the number. A
    circuit with no measured stop in those years has no key, never 0.
    '''
    measured = defaultdict(list)
    skipped = defaultdict(lambda: defaultdict(int))
    for stop in losses:
        if stop["year"] not in years:
            continue
        if stop["loss"] is None:
            skipped[stop["circuit"]][stop["skip_reason"]] += 1
        else:
            measured[stop["circuit"]].append(stop["loss"])

    result = {}
    for circuit, values in measured.items():
        q25, _, q75 = quantiles(values, n=4, method="inclusive")
        result[circuit] = {"median": median(values), "q25": q25, "q75": q75,
                           "measured": len(values), "skipped": dict(skipped[circuit])}
    return result
