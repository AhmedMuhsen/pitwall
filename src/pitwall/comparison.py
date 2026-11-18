"""Compares a small set of strategies with the simulator and tests how assumptions change the ranking."""
from collections import defaultdict
from statistics import median

import pandas as pd
import pyarrow.parquet as pq

from pitwall.analysis import lap_one_losses, max_clean_tyre_age, pit_loss_by_circuit, residual_trends, stop_losses
from pitwall.backtest import actual_strategy, first_half_pace
from pitwall.evaluation import leave_one_year_out
from pitwall.features import add_delta, add_race_fraction, driver_reference_laps
from pitwall.model import PooledWearModel
from pitwall.processing import race_distance
from pitwall.simulator import observed_max_ages, simulate, validate_strategy

# Final model and training years: DECISIONS 2026-11-17 and 2026-11-18.
FINAL_ALPHA = 100_000
TRAIN_YEARS = [2023, 2024]
BASELINE = "1stop_MH_early"


def candidate_strategies(race_distance: int) -> dict[str, dict]:
    '''
    The fixed set of strategies compared at every circuit (Week 7).

    race_distance: number of laps in the race

    returns: dict name -> strategy (new sets only), pit laps as a share of the
    race, rounded down:
        "1stop_MH_early": MEDIUM -> HARD, pit at 35%
        "1stop_MH_late":  MEDIUM -> HARD, pit at 50%
        "1stop_HM":       HARD -> MEDIUM, pit at 60%
        "2stop_MHH":      MEDIUM -> HARD -> HARD, pits at 33% and 67%
        "2stop_SHH":      SOFT -> HARD -> HARD, pits at 25% and 60%
    Chosen from what drivers ran in 2023-2024 at these circuits (mostly
    MEDIUM -> HARD, one or two stops, a SOFT start at Sakhir and Hungaroring),
    plus one reverse order. It is a small set to compare, not a search.

    raises ValueError if the race is too short for every strategy to have
    distinct pit laps (validate_strategy's message).
    '''
    d = race_distance
    strategies = {
        "1stop_MH_early": {"compounds": ["MEDIUM", "HARD"], "pit_laps": [d * 35 // 100]},
        "1stop_MH_late": {"compounds": ["MEDIUM", "HARD"], "pit_laps": [d * 50 // 100]},
        "1stop_HM": {"compounds": ["HARD", "MEDIUM"], "pit_laps": [d * 60 // 100]},
        "2stop_MHH": {"compounds": ["MEDIUM", "HARD", "HARD"], "pit_laps": [d // 3, d * 2 // 3]},
        "2stop_SHH": {"compounds": ["SOFT", "HARD", "HARD"], "pit_laps": [d * 25 // 100, d * 60 // 100]},
    }
    for strategy in strategies.values():
        validate_strategy(strategy, race_distance)
    return strategies


def compare_strategies(strategies: dict[str, dict], race_distance: int, circuit: str, model,
                       reference_lap: float, pit_loss: float, lap_one_loss: float, max_ages: dict,
                       baseline: str, wear_offset: float = 0.0) -> list[dict]:
    '''
    Simulated total time of each strategy, ranked, with the gap to a baseline strategy.

    strategies: dict name -> strategy, as in simulator.strategy_laps
    race_distance, circuit, model, reference_lap, pit_loss, lap_one_loss,
        max_ages: as in simulator.simulate
    baseline: name of the strategy the gaps are measured against
    wear_offset: extra wear in seconds per lap of tyre age, added to every
        compound (sensitivity test). The model is linear in tyre age, so this
        adds wear_offset * sum(tyre_age) to the total.

    returns: one dict per strategy, fastest first, with "strategy", "total"
    (seconds), "gap" (total minus the baseline's; positive = slower), "rank"
    (1 = fastest), "flags" (stint_range_flags messages) and "error". A
    strategy the simulator refuses keeps a row at the end with total, gap and
    rank None and the message in "error".

    raises ValueError if baseline isn't in strategies or can't be simulated.
    '''
    if baseline not in strategies:
        raise ValueError(f"Baseline {baseline!r} is not one of {sorted(strategies)}")
    results = []
    for name, strategy in strategies.items():
        row = {"strategy": name, "total": None, "gap": None, "rank": None, "flags": [], "error": None}
        try:
            sim = simulate(strategy, race_distance, circuit, model, reference_lap,
                           pit_loss, lap_one_loss, max_ages)
        except ValueError as e:
            row["error"] = str(e)
        else:
            row["total"] = sim["total_time"] + wear_offset * float(sim["laps"]["tyre_age"].sum())
            row["flags"] = sim["flags"]
        results.append(row)

    totals = {row["strategy"]: row["total"] for row in results}
    if totals[baseline] is None:
        raise ValueError(f"Baseline {baseline!r} can't be simulated: "
                         f"{next(r['error'] for r in results if r['strategy'] == baseline)}")
    ranked = sorted((r for r in results if r["total"] is not None), key=lambda r: r["total"])
    for rank, row in enumerate(ranked, start=1):
        row["rank"] = rank
        row["gap"] = row["total"] - totals[baseline]
    return ranked + [r for r in results if r["total"] is None]


def sensitivity(strategies: dict[str, dict], race_distance: int, circuit: str, model,
                reference_lap: float, pit_losses: dict[str, float], lap_one_loss: float,
                max_ages: dict, baseline: str, wear_offsets: list[float]) -> list[dict]:
    '''
    compare_strategies rerun for every pit-loss value and wear offset.

    pit_losses: dict label -> pit loss in seconds, e.g. {"q25": 20.1,
        "median": 21.0, "q75": 22.4} from analysis.pit_loss_by_circuit
    wear_offsets: extra wear values in seconds per lap of age, e.g.
        [-0.05, 0.0, 0.05]
    other arguments: as in compare_strategies

    returns: compare_strategies rows, each with "pit_loss_label", "pit_loss"
    and "wear_offset" added, for every (pit loss, wear offset) scenario.

    raises ValueError as compare_strategies does.
    '''
    rows = []
    for label, pit_loss in pit_losses.items():
        for offset in wear_offsets:
            for row in compare_strategies(strategies, race_distance, circuit, model, reference_lap,
                                          pit_loss, lap_one_loss, max_ages, baseline, offset):
                rows.append({"pit_loss_label": label, "pit_loss": pit_loss, "wear_offset": offset, **row})
    return rows


def load_dataset(path) -> list[dict]:
    '''
    Processed lap dataset rows, ready for the model.

    path: the lap dataset parquet file (data/processed/lap_dataset.parquet)

    returns: list of dicts, one per lap, with "delta" (lap time minus the
    driver's median clean lap in that race, None if either is missing) and
    "race_fraction" added.

    raises FileNotFoundError if the file doesn't exist, ValueError if it has no rows.
    '''
    rows = pq.read_table(path).to_pylist()
    # Each race's reference comes from that race's own clean laps (DECISIONS 2026-11-12).
    rows = add_delta(rows, driver_reference_laps(rows))
    return add_race_fraction(rows)


def fit_final_model(rows: list[dict]) -> PooledWearModel:
    '''
    The final model, PooledWearModel(FINAL_ALPHA, "race_fraction"), fitted on the
    clean rows that have a delta.

    rows: load_dataset rows for the training years only
    returns: the fitted model
    raises ValueError if no row is clean with a delta.
    '''
    train = pd.DataFrame([r for r in rows if r["is_clean"] and r["delta"] is not None])
    if train.empty:
        raise ValueError("No clean laps with a delta to fit on")
    return PooledWearModel(FINAL_ALPHA, "race_fraction").fit(train, train["delta"])


def held_out_wear_errors(rows: list[dict], years: list[int]) -> list[float]:
    '''
    How far off the wear rate was on a year the model didn't see.

    rows: load_dataset rows
    years: the years to swap, e.g. [2023, 2024]: each year's safety-car-free
        races are scored by the final model fitted on the other years

    returns: |leftover tyre-age slope| in seconds per lap of age, one per
    compound per race (analysis.residual_trends); compounds it skips are left out.
    '''
    errors = []
    for _, fold_train, fold_validation in leave_one_year_out(rows, years):
        model = fit_final_model(fold_train)
        safety_car = {r["session_key"] for r in fold_validation if "safety_car" in r["exclusion_reasons"]}
        trends = residual_trends([r for r in fold_validation if r["session_key"] not in safety_car], model)
        errors += [abs(t["tyre_age_slope"]) for t in trends if t["tyre_age_slope"] is not None]
    return errors


def fit_inputs(rows: list[dict], train_years: list[int] = TRAIN_YEARS) -> dict:
    '''
    Everything the comparison needs that is estimated from the training years.

    rows: load_dataset rows (any years; only train_years are used)
    train_years: years to fit on

    returns: dict with
        "model": fit_final_model on train_years
        "pit_loss": analysis.pit_loss_by_circuit dict (median, q25, q75 per circuit)
        "lap_one_loss": dict circuit -> median lap-1 loss in seconds
        "max_ages": dict (circuit, compound) -> oldest clean tyre age
        "held_out_wear_errors": held_out_wear_errors over train_years
        "wear_range": 75th percentile of those errors (s per lap of age),
            the wear sensitivity range (DECISIONS 2026-11-18)

    raises ValueError if fewer than two train_years (the wear range needs a
    held-out year) or a year has no rows.
    '''
    if len(train_years) < 2:
        raise ValueError(f"Need at least two training years for the wear range, got {train_years}")
    train = [r for r in rows if r["year"] in train_years]
    missing = set(train_years) - {r["year"] for r in train}
    if missing:
        raise ValueError(f"No rows for year(s): {sorted(missing)}")
    model = fit_final_model(train)
    lap_one = pit_loss_by_circuit(lap_one_losses(train, model), train_years)
    errors = held_out_wear_errors(rows, train_years)
    return {
        "model": model,
        "pit_loss": pit_loss_by_circuit(stop_losses(train, model), train_years),
        "lap_one_loss": {circuit: values["median"] for circuit, values in lap_one.items()},
        "max_ages": observed_max_ages(max_clean_tyre_age(train), train_years),
        "held_out_wear_errors": errors,
        "wear_range": float(pd.Series(errors).quantile(0.75)),
    }


def race_settings(rows: list[dict], inputs: dict, circuit: str, year: int) -> dict:
    '''
    The race-specific values for comparing strategies at one race.

    rows: load_dataset rows
    inputs: fit_inputs result
    circuit, year: the race

    returns: dict with "race_distance" (laps), "reference_lap" (median of the
    drivers' median clean laps in that race, seconds), "pit_losses" (dict
    "q25"/"median"/"q75" -> seconds) and "lap_one_loss" (seconds). The
    reference lap and lap-1 loss add the same time to every strategy, so they
    change totals but never a ranking.

    raises ValueError if the race isn't in rows, or the circuit has no pit
    loss or lap-1 loss in the training years.
    '''
    race = [r for r in rows if r["circuit"] == circuit and r["year"] == year]
    if not race:
        raise ValueError(f"No race for {circuit} {year} in the dataset")
    if circuit not in inputs["pit_loss"]:
        raise ValueError(f"No measured pit stops at {circuit} in the training years")
    if circuit not in inputs["lap_one_loss"]:
        raise ValueError(f"No lap-1 loss at {circuit} in the training years")
    return {
        "race_distance": race_distance(race),
        "reference_lap": median(driver_reference_laps(race).values()),
        "pit_losses": {label: inputs["pit_loss"][circuit][label] for label in ("q25", "median", "q75")},
        "lap_one_loss": inputs["lap_one_loss"][circuit],
    }


def compare_race(rows: list[dict], inputs: dict, circuit: str, year: int) -> dict:
    '''
    The candidate strategies at one race: ranking, sensitivity and lap times.

    rows, inputs, circuit, year: as in race_settings

    returns: dict with
        "settings": race_settings result
        "ranking": compare_strategies rows at the median pit loss, no wear offset
        "sensitivity": sensitivity rows over pit loss q25/median/q75 and wear
            offset -wear_range, 0, +wear_range
        "laps": DataFrame with "strategy", "lap_number" and "lap_time"
            (seconds, pit loss not included) for every strategy the simulator accepts
        "strategies": candidate_strategies for this race distance

    raises ValueError as race_settings, candidate_strategies and compare_strategies do.
    '''
    settings = race_settings(rows, inputs, circuit, year)
    strategies = candidate_strategies(settings["race_distance"])
    return {"settings": settings, "strategies": strategies,
            **_compare_all(strategies, settings, circuit, inputs, BASELINE)}


def _compare_all(strategies: dict, settings: dict, circuit: str, inputs: dict, baseline: str) -> dict:
    """Ranking at the median pit loss, the sensitivity grid rows, and simulated lap times
    (pit loss not included) of every strategy the simulator accepts."""
    shared = (settings["race_distance"], circuit, inputs["model"], settings["reference_lap"])
    ranking = compare_strategies(strategies, *shared, settings["pit_losses"]["median"],
                                 settings["lap_one_loss"], inputs["max_ages"], baseline)
    wear = inputs["wear_range"]
    rows_sensitivity = sensitivity(strategies, *shared, settings["pit_losses"], settings["lap_one_loss"],
                                   inputs["max_ages"], baseline, [-wear, 0.0, wear])
    frames = []
    for row in ranking:
        if row["error"] is None:
            sim = simulate(strategies[row["strategy"]], *shared, settings["pit_losses"]["median"],
                           settings["lap_one_loss"], inputs["max_ages"])
            frames.append(sim["laps"][["lap_number", "lap_time"]].assign(strategy=row["strategy"]))
    return {"ranking": ranking, "sensitivity": rows_sensitivity, "laps": pd.concat(frames, ignore_index=True)}


def comparable_races(rows: list[dict]) -> list[tuple[int, str]]:
    '''
    Races whose real times can be compared with the simulator: no safety-car laps.

    rows: load_dataset rows
    returns: sorted list of (year, circuit), newest year first, circuits A-Z.
    '''
    races, safety_car = set(), set()
    for row in rows:
        races.add((row["year"], row["circuit"]))
        if "safety_car" in row["exclusion_reasons"]:
            safety_car.add((row["year"], row["circuit"]))
    return sorted(races - safety_car, key=lambda race: (-race[0], race[1]))


def _race_rows(rows: list[dict], circuit: str, year: int) -> list[dict]:
    """One race's rows; raises ValueError if missing or it has safety-car laps."""
    race = [r for r in rows if r["circuit"] == circuit and r["year"] == year]
    if not race:
        raise ValueError(f"No race for {circuit} {year} in the dataset")
    if any("safety_car" in r["exclusion_reasons"] for r in race):
        raise ValueError(f"{circuit} {year} had a safety car; the simulator has none, so real times can't be compared")
    return race


def driver_choices(rows: list[dict], circuit: str, year: int, model=None, min_clean_laps: int = 5) -> list[int]:
    '''
    Drivers whose race can be compared: same rules as backtest.backtest_race.

    rows: load_dataset rows
    circuit, year: a race from comparable_races
    model: fitted model; if given, a driver also needs at least min_clean_laps clean
        laps in the first half of the race, because that is where compare_driver
        takes the pace from (backtest.first_half_pace)

    returns: sorted driver numbers with a lap time on every lap 1..race
    distance (so lapped and retired drivers are left out) and, if model is None,
    at least one clean lap.

    raises ValueError if the race isn't in rows or had a safety car.
    '''
    race = _race_rows(rows, circuit, year)
    distance = race_distance(race)
    references = driver_reference_laps(race)
    timed = defaultdict(set)
    by_driver = defaultdict(list)
    for row in race:
        by_driver[row["driver_number"]].append(row)
        if row["lap_duration"] is not None:
            timed[row["driver_number"]].add(row["lap_number"])
    session = race[0]["session_key"]
    choices = []
    for driver, laps in timed.items():
        if not set(range(1, distance + 1)) <= laps:
            continue
        if model is None:
            ok = (session, driver) in references
        else:
            ok = first_half_pace(by_driver[driver], model, distance, min_clean_laps) is not None
        if ok:
            choices.append(driver)
    return sorted(choices)


def compare_driver(rows: list[dict], inputs: dict, circuit: str, year: int, driver: int,
                   min_clean_laps: int = 5) -> dict:
    '''
    One driver's real strategy against the candidate strategies (SPEC section 1).

    rows, inputs, circuit, year: as in race_settings; the race must have no safety car
    driver: driver number, one of driver_choices
    min_clean_laps: first-half clean laps needed to estimate the car's pace

    returns: dict with
        "settings": race_settings, with "reference_lap" this car's pace: the median over
            its first-half clean laps of lap time minus the model's delta
            (backtest.first_half_pace), so the strategy being tested doesn't set the pace
        "actual_strategy": backtest.actual_strategy (used sets keep their start age)
        "actual_time": the driver's real race time, sum of lap times, seconds
        "simulated_actual": simulated time of that strategy, seconds
        "model_error": simulated_actual minus actual_time (positive = model too slow)
        "strategies": {"actual": actual_strategy, **candidate_strategies}; a candidate
            that starts on the real first compound starts on the real first set (same
            tyre age, e.g. used qualifying tyres), every other set is new
        "ranking", "sensitivity", "laps": as in compare_race, with gaps measured
            against "actual" (model vs model, so the shared model error cancels)
        "real_laps": DataFrame with "lap_number" and "lap_time", the real lap
            times (in-laps and out-laps include the time lost in the pit lane)

    raises ValueError if the race had a safety car, the driver isn't in
    driver_choices (including too few clean first-half laps), or the simulator
    refuses the driver's real strategy.
    '''
    race = _race_rows(rows, circuit, year)
    if driver not in driver_choices(rows, circuit, year, inputs["model"], min_clean_laps):
        raise ValueError(f"Car {driver} didn't run every lap of {circuit} {year} with a time "
                         "(lapped, retired or missing data), so it can't be compared")
    settings = race_settings(rows, inputs, circuit, year)
    distance = settings["race_distance"]
    laps = sorted((r for r in race if r["driver_number"] == driver and r["lap_number"] <= distance),
                  key=lambda r: r["lap_number"])
    settings["reference_lap"] = first_half_pace(laps, inputs["model"], distance, min_clean_laps)
    actual = actual_strategy(laps)
    # Everyone starts the race on the set they started on; only later sets are a free choice.
    strategies = {"actual": actual}
    for name, candidate in candidate_strategies(distance).items():
        first_age = actual["start_ages"][0] if candidate["compounds"][0] == actual["compounds"][0] else 0
        strategies[name] = {**candidate, "start_ages": [first_age] + [0] * (len(candidate["compounds"]) - 1)}
    result = _compare_all(strategies, settings, circuit, inputs, "actual")
    actual_time = sum(r["lap_duration"] for r in laps)
    simulated = next(r["total"] for r in result["ranking"] if r["strategy"] == "actual")
    return {"settings": settings, "actual_strategy": actual, "actual_time": actual_time,
            "simulated_actual": simulated, "model_error": simulated - actual_time,
            "strategies": strategies, **result,
            "real_laps": pd.DataFrame({"lap_number": [r["lap_number"] for r in laps],
                                       "lap_time": [r["lap_duration"] for r in laps]})}


def fastest_by_scenario(sensitivity_rows: list[dict]) -> pd.DataFrame:
    '''
    The fastest strategy in each sensitivity scenario, as a grid.

    sensitivity_rows: sensitivity (or compare_race "sensitivity") rows
    returns: DataFrame, one row per pit-loss label (in the order first seen),
    one column per wear offset (ascending), each cell the rank-1 strategy name.
    raises ValueError if no row has rank 1.
    '''
    winners = pd.DataFrame([r for r in sensitivity_rows if r["rank"] == 1])
    if winners.empty:
        raise ValueError("No ranked strategy in the sensitivity rows")
    grid = winners.pivot_table(index="pit_loss_label", columns="wear_offset", values="strategy", aggfunc="first")
    return grid.loc[list(dict.fromkeys(winners["pit_loss_label"]))]


def gap_ranges(sensitivity_rows: list[dict], baseline: str, base_pit_label: str = "median") -> list[dict]:
    '''
    For each strategy: its gap to the baseline at the best estimate, and how far
    that gap moves across the sensitivity scenarios.

    sensitivity_rows: sensitivity (or compare_race / compare_driver "sensitivity") rows
    baseline: the strategy the gaps are measured against
    base_pit_label: the pit-loss label of the best estimate (with wear offset 0)

    returns: one dict per strategy the simulator accepted, smallest gap first, with
    "strategy", "gap" (best estimate, seconds; negative = faster than the baseline),
    "min_gap" and "max_gap" (over every scenario), "flagged" (any stint beyond the
    observed tyre ages) and "confidence": "baseline", "faster in every scenario"
    (max_gap < 0), "slower in every scenario" (min_gap > 0) or "depends on assumptions".

    raises ValueError if no row is the best-estimate scenario.
    '''
    by_strategy = {}
    for row in sensitivity_rows:
        if row["gap"] is None:
            continue
        entry = by_strategy.setdefault(row["strategy"], {"strategy": row["strategy"], "gap": None, "gaps": [],
                                                         "flagged": bool(row["flags"])})
        entry["gaps"].append(row["gap"])
        if row["pit_loss_label"] == base_pit_label and row["wear_offset"] == 0.0:
            entry["gap"] = row["gap"]
    if not by_strategy or any(e["gap"] is None for e in by_strategy.values()):
        raise ValueError(f"No best-estimate scenario (pit loss {base_pit_label!r}, wear offset 0) in the rows")

    result = []
    for entry in by_strategy.values():
        gaps = entry.pop("gaps")
        entry["min_gap"], entry["max_gap"] = min(gaps), max(gaps)
        if entry["strategy"] == baseline:
            entry["confidence"] = "baseline"
        elif entry["max_gap"] < 0:
            entry["confidence"] = "faster in every scenario"
        elif entry["min_gap"] > 0:
            entry["confidence"] = "slower in every scenario"
        else:
            entry["confidence"] = "depends on assumptions"
        result.append(entry)
    return sorted(result, key=lambda e: e["gap"])


def verdict(ranges: list[dict], close: float = 3.0, strong: float = 10.0) -> dict:
    '''
    The one-line answer: does the model prefer an alternative to the baseline?

    ranges: gap_ranges result. Flagged alternatives (tyres older than anything
        observed) are never the answer: their totals are extrapolations.
    close, strong: seconds over the race. In the strategy-pair check (DECISIONS
        2026-11-18), the model's predicted faster car really was faster only about
        half the time under 3 s, about 2 times in 3 from 3 to 10 s and about 9
        times in 10 above 10 s.

    returns: dict with "kind", "strategy" (the best alternative, or None), "range"
    (its gap_ranges entry, or None) and "robust" (True if it is faster in every
    sensitivity scenario). "kind" is:
        "agrees": no unflagged alternative is faster at the best estimate
        "too_close": the best alternative is faster by less than `close`
        "leans": faster by `close` up to `strong`
        "prefers": faster by `strong` or more
    '''
    alternatives = [r for r in ranges if r["confidence"] != "baseline" and not r["flagged"]]
    best = min(alternatives, key=lambda r: r["gap"], default=None)
    if best is None or best["gap"] >= 0:
        return {"kind": "agrees", "strategy": None, "range": None, "robust": False}
    size = -best["gap"]
    kind = "too_close" if size < close else "leans" if size < strong else "prefers"
    return {"kind": kind, "strategy": best["strategy"], "range": best,
            "robust": best["confidence"] == "faster in every scenario"}


def cumulative_gap(laps: pd.DataFrame, strategies: dict[str, dict], pit_loss: float,
                   strategy: str, baseline: str) -> pd.DataFrame:
    '''
    Running time difference between two simulated strategies, lap by lap.

    laps: compare_race / compare_driver "laps" (strategy, lap_number, lap_time
        without pit loss)
    strategies: name -> strategy, for the pit laps
    pit_loss: seconds added on each strategy's pit laps (in-laps)
    strategy, baseline: the two strategies to compare

    returns: DataFrame with "lap_number" and "gap": strategy's elapsed time minus
    the baseline's after that lap, seconds (positive = behind). Pit stops show
    as steps, tyre wear as slopes; the last lap's gap is the race-total gap.

    raises ValueError if either strategy has no simulated laps.
    '''
    elapsed = {}
    for name in (strategy, baseline):
        own = laps[laps["strategy"] == name].sort_values("lap_number")
        if own.empty:
            raise ValueError(f"No simulated laps for {name!r}")
        times = own["lap_time"] + own["lap_number"].isin(strategies[name]["pit_laps"]) * pit_loss
        elapsed[name] = times.cumsum().to_numpy()
    return pd.DataFrame({"lap_number": sorted(laps.loc[laps["strategy"] == strategy, "lap_number"]),
                         "gap": elapsed[strategy] - elapsed[baseline]})
