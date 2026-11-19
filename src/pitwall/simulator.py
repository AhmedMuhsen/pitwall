"""Turns a pit strategy into predicted lap times and a race total."""

import pandas as pd

DRY_COMPOUNDS = {"SOFT", "MEDIUM", "HARD"}


def validate_strategy(strategy: dict, race_distance: int) -> None:
    '''
    Raises ValueError if a strategy can't happen in a dry race; returns None if it can.

    strategy: dict with "compounds", "pit_laps" and optional "start_ages", as in
        strategy_laps
    race_distance: number of laps in the race

    Checks: race_distance is at least 2; every compound is a dry compound
    (SOFT, MEDIUM, HARD; v1 simulates dry races only); at least two different
    dry compounds are used (FIA Sporting Regulations: unless intermediate or
    wet tyres are used, each driver must use at least two different
    specifications of dry-weather tyres during the race); one pit lap per
    stop; pit laps strictly increasing and between 1 and race_distance - 1, so
    every stint has at least one lap; start_ages, if given, one per stint and
    none negative. The message names the first problem found.
    '''
    compounds = strategy["compounds"]
    pit_laps = strategy["pit_laps"]
    if race_distance < 2:
        raise ValueError(f"race_distance must be at least 2, got {race_distance}")
    unknown = [c for c in compounds if c not in DRY_COMPOUNDS]
    if unknown:
        raise ValueError(f"Not dry compounds: {unknown}; expected {sorted(DRY_COMPOUNDS)}")
    if len(set(compounds)) < 2:
        raise ValueError(f"A dry race needs at least two different dry compounds, got {compounds}")
    if len(pit_laps) != len(compounds) - 1:
        raise ValueError(f"pit_laps needs {len(compounds) - 1} entries for {len(compounds)} compounds, got {len(pit_laps)}")
    if any(a >= b for a, b in zip(pit_laps, pit_laps[1:])):
        raise ValueError(f"pit_laps must be strictly increasing, got {pit_laps}")
    outside = [p for p in pit_laps if not 1 <= p <= race_distance - 1]
    if outside:
        raise ValueError(f"pit_laps must be between 1 and {race_distance - 1}, got {outside}")
    start_ages = strategy.get("start_ages")
    if start_ages is not None:
        if len(start_ages) != len(compounds):
            raise ValueError(f"start_ages needs {len(compounds)} entries, got {len(start_ages)}")
        if any(age < 0 for age in start_ages):
            raise ValueError(f"start_ages can't be negative, got {start_ages}")


def strategy_laps(strategy: dict, race_distance: int, circuit: str) -> pd.DataFrame:
    '''
    One row per race lap with the model inputs that a strategy implies.

    strategy: dict with "compounds" (list of str, one per stint, in order),
        "pit_laps" (list of int, one fewer than compounds) and optionally
        "start_ages" (list of int, tyre age of each stint's set at its first
        lap; defaults to 0 for every stint, i.e. new sets)
    race_distance: number of laps in the race
    circuit: circuit name, as in the dataset

    returns: DataFrame with "lap_number" (1..race_distance), "stint" (1-based),
        "compound", "tyre_age", "race_fraction" (lap_number / race_distance)
        and "circuit". Pitting on lap N means lap N is the last lap on the old
        set and lap N+1 is the new set's first lap at its start age, the same
        convention as the dataset's tyre_age. Tyre age resets at each stop;
        race_fraction (the fuel proxy) does not.

    raises ValueError if pit_laps or start_ages don't match the number of
    compounds. Pit laps that are out of order or outside the race are not
    checked here (see strategy validation).
    '''
    compounds = strategy["compounds"]
    pit_laps = strategy["pit_laps"]
    start_ages = strategy.get("start_ages", [0] * len(compounds))
    if len(pit_laps) != len(compounds) - 1:
        raise ValueError(f"pit_laps needs {len(compounds) - 1} entries for {len(compounds)} compounds, got {len(pit_laps)}")
    if len(start_ages) != len(compounds):
        raise ValueError(f"start_ages needs {len(compounds)} entries, got {len(start_ages)}")

    # Stint i covers laps boundaries[i]+1 .. boundaries[i+1].
    boundaries = [0] + list(pit_laps) + [race_distance]
    rows = []
    for i, compound in enumerate(compounds):
        first_lap = boundaries[i] + 1
        for lap in range(first_lap, boundaries[i + 1] + 1):
            rows.append({
                "lap_number": lap,
                "stint": i + 1,
                "compound": compound,
                "tyre_age": start_ages[i] + (lap - first_lap),
                "race_fraction": lap / race_distance,
                "circuit": circuit,
            })
    return pd.DataFrame(rows)


def observed_max_ages(table: dict, years: list[int]) -> dict[tuple, int]:
    '''
    Oldest clean-lap tyre age per (circuit, compound) across the given years.

    table: dict (circuit, year, compound) -> oldest clean tyre age, from
        analysis.max_clean_tyre_age
    years: the years to combine (the model's training years)

    returns: dict (circuit, compound) -> highest age in any of those years.
    A pair with no clean laps in those years has no key, never 0.
    '''
    result: dict[tuple, int] = {}
    for (circuit, year, compound), age in table.items():
        if year in years:
            key = (circuit, compound)
            result[key] = max(result.get(key, age), age)
    return result


def stint_range_flags(strategy: dict, race_distance: int, circuit: str, max_ages: dict) -> list[str]:
    '''
    Warnings for stints that run tyres older than anything seen in the data (rule 6).

    strategy, race_distance, circuit: as in strategy_laps
    max_ages: dict (circuit, compound) -> oldest clean tyre age, from
        observed_max_ages

    returns: list of messages, one per stint whose oldest racing lap is older
    than max_ages for its compound at this circuit; empty if none. For a stint
    that ends in a stop, its last lap is the in-lap, which is never a clean lap,
    so the lap before it is compared instead; the final stint's last lap counts.

    raises ValueError if a compound has no data at all at this circuit.
    '''
    laps = strategy_laps(strategy, race_distance, circuit)
    final_stint = len(strategy["compounds"])
    flags = []
    for stint, group in laps.groupby("stint"):
        compound = group["compound"].iloc[0]
        observed = max_ages.get((circuit, compound))
        if observed is None:
            raise ValueError(f"No clean laps for {compound}@{circuit} in the data; can't simulate this stint")
        oldest = int(group["tyre_age"].max())
        if stint != final_stint:
            oldest -= 1
        if oldest > observed:
            flags.append(f"Stint {stint} {compound}@{circuit} reaches age {oldest}; "
                         f"oldest clean lap seen is age {observed}")
    return flags


def simulate(strategy: dict, race_distance: int, circuit: str, model,
             reference_lap: float, pit_loss: float, lap_one_loss: float, max_ages: dict) -> dict:
    '''
    Predicted lap times and total race time for one strategy.

    strategy, race_distance, circuit: as in strategy_laps
    model: fitted model whose predict(DataFrame) returns the delta in seconds
        to the driver's median clean lap (Model B pipeline, PooledWearModel)
    reference_lap: the driver's median clean lap in this race, in seconds
    pit_loss: time lost per stop in seconds (pit-lane time minus the same
        stretch at racing speed), added once per stop
    lap_one_loss: extra time on lap 1 in seconds (standing start), added
        to lap 1's lap_time; from analysis.lap_one_losses
    max_ages: dict (circuit, compound) -> oldest clean tyre age in the
        training years, from observed_max_ages

    returns: dict with
        "laps": strategy_laps table plus "predicted_delta" and "lap_time"
            (reference_lap + predicted_delta, plus lap_one_loss on lap 1)
        "pit_stops": number of stops
        "total_time": sum of lap_time plus pit_stops * pit_loss, in seconds
        "flags": stint_range_flags messages; the total is still computed,
            but a flagged stint relies on tyre ages the model never saw
    In-laps and out-laps are predicted as normal laps; pit_loss stands for
    all of their extra cost.

    raises ValueError if the strategy fails validate_strategy, a compound has
    no data at this circuit, the model can't predict a lap (a compound or
    compound@circuit pair it never saw) or returns a missing prediction.
    '''
    validate_strategy(strategy, race_distance)
    flags = stint_range_flags(strategy, race_distance, circuit, max_ages)
    laps = strategy_laps(strategy, race_distance, circuit)
    laps["predicted_delta"] = model.predict(laps)
    # A NaN would make the total NaN without saying which lap caused it.
    missing = laps.loc[laps["predicted_delta"].isna(), "lap_number"].tolist()
    if missing:
        raise ValueError(f"Model returned missing predictions for laps {missing}")
    laps["lap_time"] = reference_lap + laps["predicted_delta"]
    laps.loc[laps["lap_number"] == 1, "lap_time"] += lap_one_loss

    pit_stops = len(strategy["pit_laps"])
    return {
        "laps": laps,
        "pit_stops": pit_stops,
        "total_time": float(laps["lap_time"].sum() + pit_stops * pit_loss),
        "flags": flags,
    }
