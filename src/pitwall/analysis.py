from collections import defaultdict
from statistics import median, quantiles
from typing import Any

import numpy as np
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
        


def _residuals(model, groups: list[list[dict]]) -> list[float | None]:
    """Sum of (actual - predicted delta) over each group of rows; None for a group the model can't predict.

    Predicts everything in one call, and only goes group by group if that call
    raises ValueError (a compound or compound@circuit pair the model never saw).
    """
    try:
        predicted = model.predict(pd.DataFrame([row for group in groups for row in group]))
    except ValueError:
        if len(groups) == 1:
            return [None]
        return [_residuals(model, [group])[0] for group in groups]
    result: list[float | None] = []
    i = 0
    for group in groups:
        result.append(float(sum(row["delta"] - predicted[i + k] for k, row in enumerate(group))))
        i += len(group)
    return result


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
        skip_reason "no_out_lap", "safety_car" (either lap), "no_time"
        (either lap has no delta) or "model_cannot_predict" (a compound or
        compound@circuit pair the model never saw, e.g. a pair only on
        unclean laps); measured stops have skip_reason None.
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

    losses = _residuals(model, [[in_row, out_row] for _, in_row, out_row in measured]) if measured else []
    for (record, _, _), loss in zip(measured, losses):
        if loss is None:
            record["skip_reason"] = "model_cannot_predict"
        record["loss"] = loss
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
    skipped: dict[Any, Any] = defaultdict(lambda: defaultdict(int))
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


def lap_one_losses(rows: list[dict], model) -> list[dict]:
    '''
    Time each lap 1 cost beyond a normal racing lap (standing start, first-lap traffic).

    rows, model: as in stop_losses
    returns: one dict per lap-1 row with "circuit", "year", "session_key",
        "driver_number", "loss" (actual minus predicted delta, seconds) and
        "skip_reason" ("safety_car", "no_time", "model_cannot_predict" or
        None), the same shape as
        stop_losses, so pit_loss_by_circuit gives the median per circuit.
        The model never fits lap 1 (not a clean lap), so it predicts it as
        a normal lap; this is the gap.
    '''
    records, measured = [], []
    for row in rows:
        if row["lap_number"] != 1:
            continue
        record = {"circuit": row["circuit"], "year": row["year"], "session_key": row["session_key"],
                  "driver_number": row["driver_number"], "loss": None, "skip_reason": None}
        if "safety_car" in row["exclusion_reasons"]:
            record["skip_reason"] = "safety_car"
        elif row["delta"] is None:
            record["skip_reason"] = "no_time"
        else:
            measured.append((record, row))
        records.append(record)

    losses = _residuals(model, [[row] for _, row in measured]) if measured else []
    for (record, _), loss in zip(measured, losses):
        if loss is None:
            record["skip_reason"] = "model_cannot_predict"
        record["loss"] = loss
    return records


def residual_trends(rows: list[dict], model, min_laps: int = 30) -> list[dict]:
    '''
    How the model's leftover error (actual minus predicted delta) moves with
    race lap and with tyre age, per race: separates a race-lap (fuel, track
    evolution) error, which is the same for every strategy, from a wear error,
    which changes strategy rankings.

    rows: dataset rows with "session_key", "circuit", "year", "is_clean",
        "delta" (None if no reference) and the model's inputs ("compound",
        "tyre_age", "race_fraction")
    model: fitted model whose predict(DataFrame) returns delta in seconds;
        for a fair check, fitted without these races
    min_laps: a compound with fewer clean laps in a race is left out of the fit

    returns: one dict per race and compound with "circuit", "year",
        "session_key", "compound", "n_laps" (clean laps of that compound),
        "race_fraction_slope" (seconds over the whole race, shared by every
        compound in the race), "tyre_age_slope" (seconds per lap of tyre age
        for this compound) and "skip_reason". Per race, one linear fit:
        residual ~ race_fraction + per compound (level + tyre_age slope).
        Slopes are None, with skip_reason "too_few_laps" or
        "model_cannot_predict" (that compound), or "no_compound_fitted" /
        "collinear" (race_fraction and tyre ages can't be separated, every
        compound in the race).
    '''
    races: dict[Any, Any] = defaultdict(lambda: defaultdict(list))
    for row in rows:
        if row["is_clean"] and row["delta"] is not None:
            races[row["session_key"]][row["compound"]].append(row)

    records: list[dict[str, Any]] = []
    for session_key, by_compound in races.items():
        first = next(iter(by_compound.values()))[0]
        race_records, fitted = {}, []  # fitted: (compound, rows, residuals)
        for compound, compound_rows in sorted(by_compound.items()):
            race_records[compound] = {"circuit": first["circuit"], "year": first["year"],
                                      "session_key": session_key, "compound": compound,
                                      "n_laps": len(compound_rows), "race_fraction_slope": None,
                                      "tyre_age_slope": None, "skip_reason": None}
            if len(compound_rows) < min_laps:
                race_records[compound]["skip_reason"] = "too_few_laps"
                continue
            try:
                predicted = model.predict(pd.DataFrame(compound_rows))
            except ValueError:
                race_records[compound]["skip_reason"] = "model_cannot_predict"
                continue
            residuals = [row["delta"] - p for row, p in zip(compound_rows, predicted)]
            fitted.append((compound, compound_rows, residuals))

        if not fitted:
            for record in race_records.values():
                record["skip_reason"] = record["skip_reason"] or "no_compound_fitted"
        else:
            # Columns: race_fraction, then per compound a level and a tyre_age slope.
            rows_x: list[list[float]] = []
            y: list[float] = []
            for i, (_, compound_rows, residuals) in enumerate(fitted):
                for row, residual in zip(compound_rows, residuals):
                    columns = [0.0] * (1 + 2 * len(fitted))
                    columns[0] = row["race_fraction"]
                    columns[1 + 2 * i] = 1.0
                    columns[2 + 2 * i] = row["tyre_age"]
                    rows_x.append(columns)
                    y.append(residual)
            X = np.array(rows_x)
            # lstsq would quietly return one of many answers if columns are dependent.
            if np.linalg.matrix_rank(X) < X.shape[1]:
                for compound, _, _ in fitted:
                    race_records[compound]["skip_reason"] = "collinear"
            else:
                coefficients = np.linalg.lstsq(X, np.array(y), rcond=None)[0]
                for i, (compound, _, _) in enumerate(fitted):
                    race_records[compound]["race_fraction_slope"] = float(coefficients[0])
                    race_records[compound]["tyre_age_slope"] = float(coefficients[2 + 2 * i])
        records += race_records.values()
    return records
