"""Traffic: how much lap time a car loses running close behind another, estimated from lap timing.

The field is replayed from real lap start times. The gap to the car ahead is the time since
that car crossed the line to start the same lap number, so there is no need for the OpenF1
/intervals endpoint (only one driver of one race is cached).
"""
from bisect import bisect_right
from collections import defaultdict
from datetime import datetime

import pandas as pd

# Gap bins in seconds: [0, 0.5), [0.5, 1), [1, 1.5), [1.5, 2.5), [2.5, 4), [4, inf) and "no car ahead".
EDGES = [0.5, 1.0, 1.5, 2.5, 4.0]


def start_times(race_rows: list[dict]) -> dict[int, dict[int, float]]:
    '''
    When each car started each lap.

    race_rows: dataset rows of one race, each with "driver_number", "lap_number"
        and "date_start" (ISO timestamp string or None)

    returns: dict driver_number -> {lap_number: seconds since the epoch}; a lap
    with no date_start is left out.
    '''
    times = defaultdict(dict)
    for row in race_rows:
        if row["date_start"] is not None:
            times[row["driver_number"]][row["lap_number"]] = datetime.fromisoformat(row["date_start"]).timestamp()
    return dict(times)


def gap_ahead(time: float, lap: int, field: dict[int, dict[int, float]], exclude: int | None = None) -> float | None:
    '''
    Seconds from the nearest car ahead, at the moment `time` a car starts lap number `lap`.

    time: when the car starts the lap, seconds
    lap: the lap number
    field: start_times result
    exclude: a driver number left out of the field (the car itself)

    returns: time minus the latest start of that same lap number before `time`,
    by any other car; None if no other car started that lap earlier (the car is
    leading, or alone). A lapped car starts lap `lap` later than a car on the
    lead lap, so it is never "ahead".
    '''
    latest = None
    for driver, laps in field.items():
        started = laps.get(lap)
        if driver != exclude and started is not None and started < time and (latest is None or started > latest):
            latest = started
    return None if latest is None else time - latest


def real_gaps(race_rows: list[dict]) -> dict[tuple[int, int], float | None]:
    '''
    Gap to the car ahead for every car and lap that really happened.

    race_rows: dataset rows of one race (see start_times)
    returns: dict (driver_number, lap_number) -> gap_ahead in seconds, or None when
    no car was ahead; laps with no date_start have no key.
    '''
    field = start_times(race_rows)
    return {(driver, lap): gap_ahead(time, lap, field, driver)
            for driver, laps in field.items() for lap, time in laps.items()}


def _bin(gap: float | None, edges: list[float] = EDGES) -> int:
    """Index of the gap's bin; the last bin holds gaps over the last edge and 'no car ahead'."""
    return len(edges) if gap is None else bisect_right(edges, gap)


def fit_traffic_penalty(rows: list[dict], model) -> dict:
    '''
    Lap-time penalty by gap to the car ahead, from training rows.

    rows: dataset rows of the training years (several races), each with the columns
        of start_times plus "session_key", "is_clean", "delta" (None if no reference)
        and the model's inputs ("compound", "circuit", "tyre_age", "race_fraction")
    model: fitted model, predict(DataFrame) -> delta in seconds; fitted on these rows,
        so every compound@circuit pair is known

    returns: dict with "edges" (EDGES), "mean" (one value per gap bin, seconds) and
    "n" (laps per bin). "mean" is the average of the model's residual (actual delta
    minus predicted) over clean laps after subtracting each driver's own race average,
    which removes pace differences between drivers. The model was fitted on laps that
    include traffic, so these values are relative to an average lap: close behind a
    car is positive, free air slightly negative, and over all laps they average about
    zero. Lap 1 is left out. A bin with no laps has mean 0.0 and n 0.
    '''
    by_session = defaultdict(list)
    for row in rows:
        by_session[row["session_key"]].append(row)
    records = []
    for session, race in by_session.items():
        gaps = real_gaps(race)
        for row in race:
            gap_key = (row["driver_number"], row["lap_number"])
            if row["is_clean"] and row["delta"] is not None and row["lap_number"] > 1 and gap_key in gaps:
                records.append({**row, "session": session, "gap": gaps[gap_key]})
    df = pd.DataFrame(records)
    df["resid"] = df["delta"] - model.predict(df)
    df["resid"] -= df.groupby(["session", "driver_number"])["resid"].transform("mean")
    df["bin"] = [_bin(None if pd.isna(g) else g) for g in df["gap"]]
    grouped = df.groupby("bin")["resid"].agg(["mean", "size"])
    return {"edges": list(EDGES),
            "mean": [float(grouped["mean"].get(i, 0.0)) for i in range(len(EDGES) + 1)],
            "n": [int(grouped["size"].get(i, 0)) for i in range(len(EDGES) + 1)]}


def traffic_penalty(gap: float | None, table: dict) -> float:
    """Seconds added to a lap that starts `gap` seconds behind another car (None = no car ahead)."""
    return table["mean"][_bin(gap, table["edges"])]


def traffic_timeline(free_laps: pd.DataFrame, pit_laps: list[int], pit_loss: float,
                     real_start: dict[int, float], field: dict[int, dict[int, float]], table: dict,
                     anchor: dict[int, float] | None = None) -> dict:
    '''
    A strategy's laps with traffic, run against the replayed real field.

    free_laps: DataFrame with "lap_number" (1..n) and "lap_time" (seconds, no pit loss)
        from the simulator, i.e. the lap times in free air
    pit_laps: the strategy's in-laps; the stop adds pit_loss after that lap
    pit_loss: seconds per stop
    real_start: this car's real start time of each lap (start_times of the car)
    field: start_times of the other cars (this car left out)
    table: fit_traffic_penalty result
    anchor: None for the car's real strategy, which then sits exactly where it really
        was (its start of lap n is real_start[n]). For any other strategy, the
        "cum" of the real strategy's timeline: the car's start of lap n is taken as
        real_start[n] plus how far ahead or behind the real strategy it is
        (cum - anchor), so the model's overall error cancels and only the
        difference between the strategies moves the car through the field.

    returns: dict with "laps" (lap_number, traffic_gap in seconds or NaN when no car is
    ahead or no penalty applies, traffic_penalty, lap_time with the penalty) and "cum" (lap_number -> seconds elapsed before that lap, penalties
    and pit loss included). No penalty applies on lap 1, an in-lap or an out-lap
    (pit_loss stands for those). A lap with no real_start continues from the
    previous lap's start plus its simulated time; with no start time at all the car
    is treated as running in free air.
    '''
    rows = []
    cum = {}
    elapsed = 0.0
    previous_start = None
    previous_lap_total = 0.0
    for lap, free in zip(free_laps["lap_number"], free_laps["lap_time"]):
        cum[lap] = elapsed
        if lap in real_start:
            start = real_start[lap] + (0.0 if anchor is None else elapsed - anchor[lap])
        elif previous_start is None:
            start = None          # no start time for this car yet: its position is unknown
        else:
            start = previous_start + previous_lap_total
        eligible = lap > 1 and lap not in pit_laps and (lap - 1) not in pit_laps
        gap = gap_ahead(start, lap, field) if eligible and start is not None else None
        penalty = traffic_penalty(gap, table) if eligible else 0.0
        lap_time = float(free) + penalty
        rows.append({"lap_number": lap, "traffic_gap": gap, "traffic_penalty": penalty, "lap_time": lap_time})
        previous_lap_total = lap_time + (pit_loss if lap in pit_laps else 0.0)
        elapsed += previous_lap_total
        previous_start = start
    return {"laps": pd.DataFrame(rows), "cum": cum}


def real_lap_penalties(driver: int, race_gaps: dict, table: dict, pit_laps: list[int],
                       race_distance: int) -> dict[int, float]:
    '''
    The traffic penalty of each lap a car really drove, from where it really was.

    driver: driver number
    race_gaps: real_gaps of the race
    table: fit_traffic_penalty result
    pit_laps: the car's real in-laps
    race_distance: laps in the race

    returns: dict lap_number -> seconds for laps 2..race_distance that are not an
    in-lap or an out-lap and have a known gap (a lap with no date_start has no entry).
    '''
    penalties = {}
    for lap in range(2, race_distance + 1):
        if lap in pit_laps or lap - 1 in pit_laps:
            continue
        if (driver, lap) in race_gaps:
            penalties[lap] = traffic_penalty(race_gaps[(driver, lap)], table)
    return penalties
