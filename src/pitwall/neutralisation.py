"""Safety cars and virtual safety cars, replayed from what really happened.

PitWall runs after the race, so it knows exactly when each safety car came out. Laps under one
take the field's real lap time (not a model prediction), and a stop under a real safety car costs
a fraction of the circuit's normal pit loss. Random safety cars are out of scope (DECISIONS 2026-11-18).
"""
import json
from statistics import median, quantiles

import pandas as pd


def neutralised_windows(race_control: list[dict]) -> list[dict]:
    '''
    The safety-car and virtual-safety-car periods of one race.

    race_control: OpenF1 /race_control records of one session, each with "category",
        "message", "date" and "lap_number"

    returns: list of {"kind": "SC" or "VSC", "start": lap, "end": lap}, earliest first.
    "start" is the lap of the "DEPLOYED" message, "end" the lap of "IN THIS LAP" (safety
    car) or "ENDING" (virtual); both laps are part of the period.

    raises ValueError if a period has no start, no end, or a message has no lap number.
    '''
    events = sorted((r for r in race_control if r["category"] == "SafetyCar"), key=lambda r: r["date"])
    windows, started = [], {}
    for event in events:
        message = event["message"].upper()
        kind = "VSC" if "VIRTUAL" in message else "SC"
        lap = event["lap_number"]
        if lap is None:
            raise ValueError(f"{message!r} has no lap number")
        if "DEPLOYED" in message:
            if kind in started:
                raise ValueError(f"{kind} deployed on lap {lap} while already out since lap {started[kind]}")
            started[kind] = lap
        elif "IN THIS LAP" in message or "ENDING" in message:
            if kind not in started:
                raise ValueError(f"{kind} ended on lap {lap} but was never deployed")
            windows.append({"kind": kind, "start": started.pop(kind), "end": lap})
    if started:
        kind, lap = next(iter(started.items()))
        raise ValueError(f"{kind} deployed on lap {lap} has no end message")
    return sorted(windows, key=lambda w: w["start"])


def load_neutralisations(path) -> dict[int, list[dict]]:
    '''
    Windows written by scripts/build_neutralisations.py.

    path: data/processed/neutralisations.json
    returns: dict session_key -> neutralised_windows list; {} if the file doesn't exist.
    '''
    try:
        with open(path, encoding="utf-8") as f:
            table = json.load(f)
    except FileNotFoundError:
        return {}
    return {int(session): windows for session, windows in table.items()}


def field_lap_times(race_rows: list[dict]) -> dict[int, float]:
    '''
    The field's lap time on every lap of one race.

    race_rows: dataset rows of one race, each with "lap_number", "lap_duration",
        "is_pit_out_lap" and "exclusion_reasons"
    returns: dict lap_number -> median lap_duration over the cars that ran it with a time,
    leaving out each car's in-lap and out-lap (pit-lane laps). A lap with no such car has no key.
    '''
    by_lap = {}
    for row in race_rows:
        if row["lap_duration"] is None or row["is_pit_out_lap"] or "in_lap" in row["exclusion_reasons"]:
            continue
        by_lap.setdefault(row["lap_number"], []).append(row["lap_duration"])
    return {lap: float(median(times)) for lap, times in by_lap.items()}


def build_neutralisation(race_rows: list[dict], windows: list[dict], pit_loss_ratio: float | None) -> dict:
    '''
    Everything the simulator needs to replay a race's safety cars.

    race_rows: dataset rows of the race (see field_lap_times)
    windows: neutralised_windows of the race
    pit_loss_ratio: stop loss under a real safety car as a share of the normal pit loss
        (fit_sc_pit_loss), or None to charge the normal pit loss

    returns: dict with "lap_times" (lap -> the field's real lap time, for every lap in a
    window), "sc_laps" (laps under a real safety car; a stop whose in-lap is one of these
    is cheaper), "laps" (every neutralised lap), "no_traffic_laps" (those laps and the lap
    before and after each window: the field is bunched there, outside what the traffic
    penalty was estimated on) and "pit_loss_ratio".

    raises ValueError if a neutralised lap has no field lap time.
    '''
    times = field_lap_times(race_rows)
    laps = {lap for w in windows for lap in range(w["start"], w["end"] + 1)}
    missing = sorted(lap for lap in laps if lap not in times)
    if missing:
        raise ValueError(f"No lap times to replay on neutralised laps {missing}")
    return {"lap_times": {lap: times[lap] for lap in laps},
            "sc_laps": {lap for w in windows if w["kind"] == "SC" for lap in range(w["start"], w["end"] + 1)},
            "laps": laps, "no_traffic_laps": laps | {lap + d for lap in laps for d in (-1, 1)},
            "pit_loss_ratio": pit_loss_ratio}


def apply_neutralisation(laps: pd.DataFrame, pit_laps: list[int], pit_loss: float,
                         neutralisation: dict | None) -> tuple[pd.DataFrame, dict[int, float]]:
    '''
    Put the replayed safety cars into a simulated strategy.

    laps: simulator laps with "lap_number" and "lap_time"
    pit_laps: the strategy's in-laps
    pit_loss: the circuit's normal seconds per stop
    neutralisation: build_neutralisation result, or None for no safety cars

    returns: (laps with lap_time replaced by the field's real lap time on every neutralised
    lap, dict in-lap -> seconds that stop costs). A stop whose in-lap is under a real safety
    car costs pit_loss_ratio * pit_loss; every other stop costs pit_loss (a stop under a
    virtual safety car too: there are too few to measure a saving).
    '''
    stop_loss = {lap: pit_loss for lap in pit_laps}
    if neutralisation is None:
        return laps, stop_loss
    replay = neutralisation["lap_times"]
    laps = laps.assign(lap_time=[replay.get(lap, time) for lap, time in zip(laps["lap_number"], laps["lap_time"])])
    ratio = neutralisation["pit_loss_ratio"]
    if ratio is not None:
        for lap in pit_laps:
            if lap in neutralisation["sc_laps"]:
                stop_loss[lap] = ratio * pit_loss
    return laps, stop_loss


def fit_sc_pit_loss(rows: list[dict], windows_by_session: dict[int, list[dict]],
                    pit_loss: dict[str, dict], years: list[int]) -> dict | None:
    '''
    How much cheaper a stop is under a real safety car, from the stops really made.

    rows: dataset rows (several races)
    windows_by_session: load_neutralisations result
    pit_loss: analysis.pit_loss_by_circuit result (the normal pit loss per circuit)
    years: the training years; only their races are used

    returns: dict with "ratio" (median), "q25", "q75" and "n" (stops), or None if no stop
    was made under a real safety car in those years. A stop's loss is the in-lap plus
    out-lap time minus the field's lap time on those two laps, divided by the circuit's
    normal pit loss. Virtual safety cars are not used (too few stops, none clearly cheaper).
    '''
    by_session = {}
    for row in rows:
        if row["year"] in years and any(w["kind"] == "SC" for w in windows_by_session.get(row["session_key"], [])):
            by_session.setdefault(row["session_key"], []).append(row)
    ratios = []
    for session, race in by_session.items():
        circuit = race[0]["circuit"]
        if circuit not in pit_loss:
            continue
        field = field_lap_times(race)
        sc_laps = {lap for w in windows_by_session[session] if w["kind"] == "SC"
                   for lap in range(w["start"], w["end"] + 1)}
        laps = {(r["driver_number"], r["lap_number"]): r["lap_duration"] for r in race if r["lap_duration"] is not None}
        for row in race:
            lap, driver = row["lap_number"], row["driver_number"]
            if "in_lap" in row["exclusion_reasons"] and lap in sc_laps and (driver, lap) in laps \
                    and (driver, lap + 1) in laps and lap in field and lap + 1 in field:
                loss = laps[(driver, lap)] + laps[(driver, lap + 1)] - field[lap] - field[lap + 1]
                ratios.append(loss / pit_loss[circuit]["median"])
    if not ratios:
        return None
    q25, _, q75 = quantiles(ratios, n=4, method="inclusive") if len(ratios) > 1 else (ratios[0],) * 3
    return {"ratio": float(median(ratios)), "q25": float(q25), "q75": float(q75), "n": len(ratios)}
