"""Turns a pit strategy into predicted lap times and a race total."""
import pandas as pd


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


def simulate(strategy: dict, race_distance: int, circuit: str, model,
             reference_lap: float, pit_loss: float) -> dict:
    '''
    Predicted lap times and total race time for one strategy.

    strategy, race_distance, circuit: as in strategy_laps
    model: fitted model whose predict(DataFrame) returns the delta in seconds
        to the driver's median clean lap (Model B pipeline, PooledWearModel)
    reference_lap: the driver's median clean lap in this race, in seconds
    pit_loss: time lost per stop in seconds (pit-lane time minus the same
        stretch at racing speed), added once per stop

    returns: dict with
        "laps": strategy_laps table plus "predicted_delta" and "lap_time"
            (reference_lap + predicted_delta)
        "pit_stops": number of stops
        "total_time": sum of lap_time plus pit_stops * pit_loss, in seconds
    In-laps and out-laps are predicted as normal laps; pit_loss stands for
    all of their extra cost.

    raises ValueError if the model can't predict a lap (a compound or
    compound@circuit pair it never saw) or returns a missing prediction.
    '''
    laps = strategy_laps(strategy, race_distance, circuit)
    laps["predicted_delta"] = model.predict(laps)
    # A NaN would make the total NaN without saying which lap caused it.
    missing = laps.loc[laps["predicted_delta"].isna(), "lap_number"].tolist()
    if missing:
        raise ValueError(f"Model returned missing predictions for laps {missing}")
    laps["lap_time"] = reference_lap + laps["predicted_delta"]

    pit_stops = len(strategy["pit_laps"])
    return {
        "laps": laps,
        "pit_stops": pit_stops,
        "total_time": float(laps["lap_time"].sum() + pit_stops * pit_loss),
    }
