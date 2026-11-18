"""Real strategies run through the simulator, compared with the real race times (rule 8)."""
from collections import defaultdict

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
        minus actual, seconds; positive = predicted too slow), "flags" and
        "skip_reason". Drivers who didn't complete every lap with a time
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
                  "error": None, "flags": [], "skip_reason": None}
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
            result = simulate(actual_strategy(laps), distance, first["circuit"], model,
                              reference, pit_loss, lap_one_loss, max_ages)
        except ValueError as e:
            record["skip_reason"] = f"cannot_simulate: {e}"
            records.append(record)
            continue
        actual = sum(r["lap_duration"] for r in laps)
        record.update(predicted=result["total_time"], actual=actual,
                      error=result["total_time"] - actual, flags=result["flags"])
        records.append(record)
    return records
