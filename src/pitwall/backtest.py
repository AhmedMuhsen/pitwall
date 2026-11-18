"""Real strategies run through the simulator, compared with the real race times (rule 8)."""
from collections import defaultdict
from statistics import median

import pandas as pd

from pitwall.features import driver_reference_laps
from pitwall.processing import race_distance
from pitwall.simulator import simulate


def actual_strategy(driver_rows: list[dict]) -> dict:
    '''
    The strategy a driver really used, in the simulator's format.

    driver_rows: one driver's dataset rows in one race, any order, each with
        "lap_number", "stint_number", "compound" and "tyre_age"

    returns: dict with "compounds" (one per stint, in order), "pit_laps" (the
        lap before each new stint's first lap, i.e. the in-lap) and
        "start_ages" (tyre age on each stint's first lap, so used sets keep
        their age).

    raises ValueError if a lap has no stint_number (a lap with no stint
    can't be placed in a strategy).
    '''
    laps = sorted(driver_rows, key=lambda r: r["lap_number"])
    missing = [r["lap_number"] for r in laps if r["stint_number"] is None]
    if missing:
        raise ValueError(f"Laps with no stint: {missing}")
    firsts = {}
    for row in laps:
        firsts.setdefault(row["stint_number"], row)
    stints = [firsts[k] for k in sorted(firsts)]
    return {"compounds": [s["compound"] for s in stints],
            "pit_laps": [s["lap_number"] - 1 for s in stints[1:]],
            "start_ages": [s["tyre_age"] for s in stints]}


def error_components(driver_laps: list[dict], simulated_laps, pit_laps: list[int], pit_loss: float) -> dict:
    '''
    A driver's race-total error (predicted minus actual) split into lap 1,
    stops and normal laps; the three parts add up to the total error.

    driver_laps: the driver's dataset rows for laps 1..race distance, each
        with "lap_number" and a non-missing "lap_duration"
    simulated_laps: simulate(...)["laps"] for the driver's actual strategy
        (columns "lap_number" and "lap_time")
    pit_laps: the strategy's pit laps (in-laps)
    pit_loss: seconds added per stop in the simulation

    returns: dict with "lap_one" (lap 1, including lap_one_loss), "stops"
        (in-lap + out-lap of every stop, plus pit_loss per stop), "normal"
        (every other lap) and "normal_by_lap" (lap_number -> error of each
        normal lap), all in seconds, positive = predicted too slow. Lap 1
        always counts as lap_one, even if it is an in-lap.

    raises ValueError if the two sets of laps don't cover the same lap numbers.
    '''
    actual = {r["lap_number"]: r["lap_duration"] for r in driver_laps}
    predicted = dict(zip(simulated_laps["lap_number"], simulated_laps["lap_time"]))
    if set(actual) != set(predicted):
        raise ValueError(f"Actual laps {sorted(set(actual) ^ set(predicted))} don't match the simulated laps")

    stop_laps = {lap for p in pit_laps for lap in (p, p + 1)} - {1}
    errors = {lap: float(predicted[lap] - actual[lap]) for lap in actual}
    normal_by_lap = {lap: e for lap, e in sorted(errors.items()) if lap != 1 and lap not in stop_laps}
    return {
        "lap_one": errors[1],
        "stops": sum(errors[lap] for lap in stop_laps) + len(pit_laps) * pit_loss,
        "normal": sum(normal_by_lap.values()),
        "normal_by_lap": normal_by_lap,
    }


def backtest_race(race_rows: list[dict], model, pit_loss: float, lap_one_loss: float,
                  max_ages: dict) -> list[dict]:
    '''
    Predicted vs actual total race time for every driver in one race.

    race_rows: dataset rows of one race (one session_key) with no safety-car
        laps; columns as in actual_strategy plus "session_key",
        "driver_number", "lap_duration", "is_clean", "circuit", "year" and
        "exclusion_reasons"
    model, pit_loss, lap_one_loss, max_ages: as in simulator.simulate, all
        estimated without this race's year
    The reference lap is the driver's median clean lap in this race (rule 1).

    returns: one dict per driver with "circuit", "year", "session_key",
        "driver_number", "laps", "predicted", "actual" and "error" (predicted
        minus actual, seconds; positive = predicted too slow), "flags",
        "components" (error_components of the error) and "skip_reason".Drivers who didn't complete every lap with a time
        ("not_full_distance", e.g. lapped or retired), have no clean lap for a
        reference ("no_reference") or whose strategy the
        simulator refuses ("cannot_simulate: <message>") keep a record with
        predicted None.

    raises ValueError if race_rows has more than one session or a safety-car lap.
    '''
    sessions = {r["session_key"] for r in race_rows}
    if len(sessions) != 1:
        raise ValueError(f"Expected one race, got sessions {sorted(sessions)}")
    if any("safety_car" in r["exclusion_reasons"] for r in race_rows):
        raise ValueError("Race has safety-car laps; the simulator has no safety car, so it can't be backtested")

    distance = race_distance(race_rows)
    references = driver_reference_laps(race_rows)
    by_driver = defaultdict(list)
    for row in race_rows:
        by_driver[row["driver_number"]].append(row)

    records = []
    for driver, laps in sorted(by_driver.items()):
        first = laps[0]
        record = {"circuit": first["circuit"], "year": first["year"], "session_key": first["session_key"],
                  "driver_number": driver, "laps": distance, "predicted": None, "actual": None,
                  "error": None, "flags": [], "components": None, "skip_reason": None}
        timed = {r["lap_number"] for r in laps if r["lap_duration"] is not None}
        if not set(range(1, distance + 1)) <= timed:
            record["skip_reason"] = "not_full_distance"
            records.append(record)
            continue
        reference = references.get((first["session_key"], driver))
        if reference is None:
            record["skip_reason"] = "no_reference"
            records.append(record)
            continue
        laps = [r for r in laps if r["lap_number"] <= distance]
        try:
            strategy = actual_strategy(laps)
            result = simulate(strategy, distance, first["circuit"], model,
                              reference, pit_loss, lap_one_loss, max_ages)
        except ValueError as e:
            record["skip_reason"] = f"cannot_simulate: {e}"
            records.append(record)
            continue
        actual = sum(r["lap_duration"] for r in laps)
        record.update(predicted=result["total_time"], actual=actual,
                      error=result["total_time"] - actual, flags=result["flags"],
                      components=error_components(laps, result["laps"], strategy["pit_laps"], pit_loss))
        records.append(record)
    return records


def second_half_record(driver_rows: list[dict], model, race_distance: int, pit_loss: float,
                       max_ages: dict, min_clean_laps: int = 5) -> dict:
    '''
    One car's second half of a race: real time vs the simulator's, with the car's
    pace taken only from the first half (so the scored laps never set the pace).

    driver_rows: the car's dataset rows in one safety-car-free race, with a
        lap_duration on every lap 1..race_distance; columns as in
        actual_strategy plus "lap_duration", "is_clean", "race_fraction",
        "circuit", "year", "session_key" and "driver_number"
    model: fitted model, predict(DataFrame) -> delta in seconds; fitted
        without this race's year
    race_distance: laps in the race; the first half is laps 1..race_distance // 2
    pit_loss, max_ages: as in simulator.simulate
    min_clean_laps: fewest first-half clean laps to estimate the pace from

    returns: dict with "session_key", "circuit", "year", "driver_number",
    "strategy" (actual_strategy), "pace" (median over first-half clean laps of
    lap_duration minus the model's predicted delta, seconds), "scored_laps"
    (laps in the second half), "real" (real second-half time), "predicted"
    (simulated second-half time from that pace, plus pit_loss for each stop in
    the second half), "stops" (stops in the second half), "pit_loss" and
    "skip_reason" ("too_few_first_half_laps" or "cannot_simulate: <message>";
    then pace, real and predicted are None).
    '''
    laps = sorted((r for r in driver_rows if r["lap_number"] <= race_distance), key=lambda r: r["lap_number"])
    first = laps[0]
    half = race_distance // 2
    strategy = actual_strategy(laps)
    stops = sum(1 for p in strategy["pit_laps"] if p > half)
    record = {"session_key": first["session_key"], "circuit": first["circuit"], "year": first["year"],
              "driver_number": first["driver_number"], "strategy": strategy, "pace": None,
              "scored_laps": race_distance - half, "real": None, "predicted": None, "stops": stops,
              "pit_loss": pit_loss, "skip_reason": None}
    clean_first = pd.DataFrame([r for r in laps if r["lap_number"] <= half and r["is_clean"]])
    if len(clean_first) < min_clean_laps:
        record["skip_reason"] = "too_few_first_half_laps"
        return record
    pace = float(median(clean_first["lap_duration"] - model.predict(clean_first)))
    try:
        # Lap 1 is never scored here, so its standing-start loss doesn't matter.
        sim = simulate(strategy, race_distance, first["circuit"], model, pace, pit_loss, 0.0, max_ages)
    except ValueError as e:
        record["skip_reason"] = f"cannot_simulate: {e}"
        return record
    second = sim["laps"]["lap_number"] > half
    record.update(pace=pace, real=sum(r["lap_duration"] for r in laps if r["lap_number"] > half),
                  predicted=float(sim["laps"].loc[second, "lap_time"].sum()) + stops * pit_loss)
    return record


def strategy_pair_errors(records: list[dict], same_within: int = 3) -> list[dict]:
    '''
    Predicted vs real second-half gap between every two cars in the same race
    that ran different strategies, with each car's own pace taken out.

    records: second_half_record results; skipped ones are left out
    same_within: two strategies with the same compounds and every pit lap
        within this many laps count as the same strategy and aren't paired

    returns: one dict per pair with "session_key", "circuit", "year", "car_a",
    "car_b" and, all in seconds for the second half (a minus b, positive = a slower):
        "real": real gap minus the pace gap ((pace_a - pace_b) * scored_laps),
            the part of the real gap that pace doesn't explain
        "predicted": the simulator's gap minus the same pace gap
        "stops_only": a baseline that only counts second-half stops:
            (stops_a - stops_b) * pit_loss
        "error": predicted minus real
    '''
    by_race = defaultdict(list)
    for record in records:
        if record["skip_reason"] is None:
            by_race[record["session_key"]].append(record)
    pairs = []
    for race in by_race.values():
        race = sorted(race, key=lambda r: r["driver_number"])
        for i, a in enumerate(race):
            for b in race[i + 1:]:
                sa, sb = a["strategy"], b["strategy"]
                if sa["compounds"] == sb["compounds"] and all(
                        abs(x - y) <= same_within for x, y in zip(sa["pit_laps"], sb["pit_laps"])):
                    continue
                pace_gap = (a["pace"] - b["pace"]) * a["scored_laps"]
                real = (a["real"] - b["real"]) - pace_gap
                predicted = (a["predicted"] - b["predicted"]) - pace_gap
                pairs.append({"session_key": a["session_key"], "circuit": a["circuit"], "year": a["year"],
                              "car_a": a["driver_number"], "car_b": b["driver_number"], "real": real,
                              "predicted": predicted, "stops_only": (a["stops"] - b["stops"]) * a["pit_loss"],
                              "error": predicted - real})
    return pairs
