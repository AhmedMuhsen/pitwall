"""Compares a small set of strategies with the simulator and tests how assumptions change the ranking.

The pieces live in strategies.py (what to compare), fitting.py (the model and its refits) and gaps.py (reading the result);
they are re-exported here so `from pitwall.comparison import ...` keeps working."""
import json
from collections import defaultdict
from statistics import median
from typing import Any

import pandas as pd

from pitwall.backtest import actual_strategy, first_half_pace
from pitwall.features import driver_reference_laps
from pitwall.fitting import (
    FINAL_ALPHA,
    TRAIN_YEARS,
    fit_ensemble,
    fit_final_model,
    fit_inputs,
    held_out_wear_errors,
    load_dataset,
)
from pitwall.gaps import (
    STINT_ERROR_FLOOR,
    cumulative_gap,
    fastest_by_scenario,
    gap_ranges,
    verdict,
)
from pitwall.neutralisation import (
    apply_neutralisation,
    build_neutralisation,
)
from pitwall.processing import race_distance
from pitwall.simulator import simulate, validate_strategy
from pitwall.strategies import (
    BASELINE,
    candidate_strategies,
    custom_strategy,
    safety_car_candidate,
    with_start_ages,
)
from pitwall.traffic import (
    real_gaps,
    real_lap_penalties,
    start_times,
    traffic_timeline,
)

__all__ = [
    "BASELINE",
    "FINAL_ALPHA",
    "STINT_ERROR_FLOOR",
    "TRAIN_YEARS",
    "candidate_strategies",
    "comparable_races",
    "compare_driver",
    "compare_race",
    "compare_strategies",
    "cumulative_gap",
    "custom_strategy",
    "driver_choices",
    "fastest_by_scenario",
    "fit_ensemble",
    "fit_final_model",
    "fit_inputs",
    "gap_ranges",
    "held_out_wear_errors",
    "load_dataset",
    "load_driver_names",
    "race_session_key",
    "race_settings",
    "safety_car_candidate",
    "sensitivity",
    "verdict",
    "with_start_ages",
]


def _run_strategy(strategy: dict, race_distance: int, circuit: str, model, reference_lap: float,
                  pit_loss: float, lap_one_loss: float, max_ages: dict, wear_offset: float,
                  traffic: dict | None, anchor: dict | None, neutralisation: dict | None = None) -> dict:
    """simulate plus the wear offset, the replayed safety cars (`neutralisation`) and the
    replayed-field timeline (`traffic`).
    Returns "total", "laps" (lap_number, lap_time without pit loss, with the traffic penalty),
    "flags" and "cum" (traffic_timeline's elapsed time per lap, None without traffic).
    Raises ValueError as simulate does."""
    sim = simulate(strategy, race_distance, circuit, model, reference_lap, pit_loss, lap_one_loss, max_ages)
    laps = sim["laps"][["lap_number", "lap_time"]].assign(
        lap_time=sim["laps"]["lap_time"] + wear_offset * sim["laps"]["tyre_age"])
    laps, stop_loss = apply_neutralisation(laps, strategy["pit_laps"], pit_loss, neutralisation)
    stops_cost = sum(stop_loss.values())
    if traffic is None:
        return {"total": float(laps["lap_time"].sum() + stops_cost), "laps": laps, "flags": sim["flags"],
                "cum": None}
    timeline = traffic_timeline(laps, strategy["pit_laps"], pit_loss, traffic["real_start"], traffic["field"],
                                traffic["table"], anchor, stop_loss,
                                frozenset() if neutralisation is None else neutralisation["no_traffic_laps"])
    laps = timeline["laps"][["lap_number", "lap_time"]]
    return {"total": float(laps["lap_time"].sum() + stops_cost), "laps": laps,
            "flags": sim["flags"], "cum": timeline["cum"]}


def compare_strategies(strategies: dict[str, dict], race_distance: int, circuit: str, model,
                       reference_lap: float, pit_loss: float, lap_one_loss: float, max_ages: dict,
                       baseline: str, wear_offset: float = 0.0, traffic: dict | None = None,
                       neutralisation: dict | None = None) -> list[dict]:
    '''
    Simulated total time of each strategy, ranked, with the gap to a baseline strategy.

    strategies: dict name -> strategy, as in simulator.strategy_laps
    race_distance, circuit, model, reference_lap, pit_loss, lap_one_loss,
        max_ages: as in simulator.simulate
    baseline: name of the strategy the gaps are measured against
    wear_offset: extra wear in seconds per lap of tyre age, added to every
        compound (sensitivity test), to the lap times before any traffic is applied
    traffic: optional dict with "table" (traffic.fit_traffic_penalty), "field" (start
        times of the other cars), "real_start" (this car's real lap start times) and
        "anchor" (the name of the strategy the car really drove, which is in
        strategies). Every strategy then runs against the replayed field
        (traffic.traffic_timeline), positioned relative to the real strategy.
    neutralisation: optional neutralisation.build_neutralisation result: laps under a safety
        car take the field's real lap time and a stop under a real safety car is cheaper.

    returns: one dict per strategy, fastest first, with "strategy", "total"
    (seconds), "gap" (total minus the baseline's; positive = slower), "rank"
    (1 = fastest), "flags" (stint_range_flags messages) and "error". A
    strategy the simulator refuses keeps a row at the end with total, gap and
    rank None and the message in "error".

    raises ValueError if baseline isn't in strategies or can't be simulated, or if the
    traffic anchor strategy isn't in strategies or can't be simulated.
    '''
    if baseline not in strategies:
        raise ValueError(f"Baseline {baseline!r} is not one of {sorted(strategies)}")
    shared = (race_distance, circuit, model, reference_lap, pit_loss, lap_one_loss, max_ages, wear_offset, traffic)
    anchor_cum = None
    if traffic is not None:
        if traffic["anchor"] not in strategies:
            raise ValueError(f"Traffic anchor {traffic['anchor']!r} is not one of {sorted(strategies)}")
        try:
            anchor_cum = _run_strategy(strategies[traffic["anchor"]], *shared, None, neutralisation)["cum"]
        except ValueError as e:
            raise ValueError(f"Traffic anchor {traffic['anchor']!r} can't be simulated: {e}") from e
    results = []
    for name, strategy in strategies.items():
        row: dict[str, Any] = {"strategy": name, "total": None, "gap": None, "rank": None, "flags": [], "error": None}
        try:
            run = _run_strategy(strategy, *shared, None if name == (traffic or {}).get("anchor") else anchor_cum,
                                neutralisation)
        except ValueError as e:
            row["error"] = str(e)
        else:
            row["total"], row["flags"] = run["total"], run["flags"]
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
                max_ages: dict, baseline: str, wear_offsets: list[float], traffic: dict | None = None,
                neutralisation: dict | None = None) -> list[dict]:
    '''
    compare_strategies rerun for every pit-loss value and wear offset.

    pit_losses: dict label -> pit loss in seconds, e.g. {"q25": 20.1,
        "median": 21.0, "q75": 22.4} from analysis.pit_loss_by_circuit
    wear_offsets: extra wear values in seconds per lap of age, e.g.
        [-0.05, 0.0, 0.05]
    traffic and the other arguments: as in compare_strategies

    returns: compare_strategies rows, each with "pit_loss_label", "pit_loss"
    and "wear_offset" added, for every (pit loss, wear offset) scenario.

    raises ValueError as compare_strategies does.
    '''
    rows = []
    for label, pit_loss in pit_losses.items():
        for offset in wear_offsets:
            for row in compare_strategies(strategies, race_distance, circuit, model, reference_lap,
                                          pit_loss, lap_one_loss, max_ages, baseline, offset, traffic, neutralisation):
                rows.append({"pit_loss_label": label, "pit_loss": pit_loss, "wear_offset": offset, **row})
    return rows


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

    raises ValueError if the race isn't in rows, the circuit has no measured pit loss in the
    training years, or there is no lap-1 loss at all (not even the all-circuit default).
    '''
    race = [r for r in rows if r["circuit"] == circuit and r["year"] == year]
    if not race:
        raise ValueError(f"No race for {circuit} {year} in the dataset")
    if circuit not in inputs["pit_loss"]:
        raise ValueError(f"No measured pit stops at {circuit} in the training years")
    lap_one_loss = inputs["lap_one_loss"].get(circuit, inputs.get("lap_one_loss_default"))
    if lap_one_loss is None:
        raise ValueError(f"No lap-1 loss at {circuit} in the training years")
    return {
        "race_distance": race_distance(race),
        "reference_lap": median(driver_reference_laps(race).values()),
        "pit_losses": {label: inputs["pit_loss"][circuit][label] for label in ("q25", "median", "q75")},
        "lap_one_loss": lap_one_loss,
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


def _compare_all(strategies: dict, settings: dict, circuit: str, inputs: dict, baseline: str,
                 traffic: dict | None = None, neutralisation: dict | None = None, light: bool = False) -> dict:
    """Ranking at the median pit loss, the sensitivity grid rows, and simulated lap times
    (pit loss not included, traffic penalty included if `traffic`) of every strategy the
    simulator accepts. `traffic` and `neutralisation` as in compare_strategies. With `light` only the
    ranking is computed (sensitivity rows and laps are empty): used for the refits."""
    shared = (settings["race_distance"], circuit, inputs["model"], settings["reference_lap"])
    pit_loss, lap_one = settings["pit_losses"]["median"], settings["lap_one_loss"]
    ranking = compare_strategies(strategies, *shared, pit_loss, lap_one, inputs["max_ages"], baseline,
                                 traffic=traffic, neutralisation=neutralisation)
    if light:
        return {"ranking": ranking, "sensitivity": [], "laps": pd.DataFrame()}
    wear = inputs["wear_range"]
    rows_sensitivity = sensitivity(strategies, *shared, settings["pit_losses"], lap_one,
                                   inputs["max_ages"], baseline, [-wear, 0.0, wear], traffic, neutralisation)
    anchor_cum = None
    if traffic is not None:
        anchor_cum = _run_strategy(strategies[traffic["anchor"]], *shared, pit_loss, lap_one, inputs["max_ages"],
                                   0.0, traffic, None, neutralisation)["cum"]
    frames = []
    for row in ranking:
        if row["error"] is None:
            is_anchor = traffic is not None and row["strategy"] == traffic["anchor"]
            run = _run_strategy(strategies[row["strategy"]], *shared, pit_loss, lap_one, inputs["max_ages"], 0.0,
                                traffic, None if is_anchor else anchor_cum, neutralisation)
            frames.append(run["laps"].assign(strategy=row["strategy"]))
    return {"ranking": ranking, "sensitivity": rows_sensitivity, "laps": pd.concat(frames, ignore_index=True)}


def comparable_races(rows: list[dict], windows: dict[int, list[dict]] | None = None,
                     inputs: dict | None = None) -> list[tuple[int, str]]:
    '''
    Races whose real times can be compared with the simulator: no safety-car laps, or the
    safety cars' windows are known so they can be replayed.

    rows: load_dataset rows
    windows: neutralisation.load_neutralisations result; a race with safety-car laps counts
        only if it has windows and every neutralised lap has a field lap time (build_neutralisation)
    inputs: fit_inputs result; if given, a race at a circuit with no measured pit loss in the
        training years is left out too (it can't be simulated)
    returns: sorted list of (year, circuit), newest year first, circuits A-Z.
    '''
    races, unreplayable, by_session = set(), set(), defaultdict(list)
    for row in rows:
        races.add((row["year"], row["circuit"]))
        by_session[row["session_key"]].append(row)
        if "safety_car" in row["exclusion_reasons"] and not (windows or {}).get(row["session_key"]):
            unreplayable.add((row["year"], row["circuit"]))
    for session, race in by_session.items():
        session_windows = (windows or {}).get(session)
        if session_windows:
            try:
                build_neutralisation(race, session_windows, None)
            except ValueError:
                unreplayable.add((race[0]["year"], race[0]["circuit"]))     # no field lap time to replay
    if inputs is not None:
        unreplayable |= {race for race in races if race[1] not in inputs["pit_loss"]}
    return sorted(races - unreplayable, key=lambda race: (-race[0], race[1]))


def _race_rows(rows: list[dict], circuit: str, year: int, windows: dict[int, list[dict]] | None = None) -> list[dict]:
    """One race's rows; raises ValueError if missing, or if it has safety-car laps and no windows to replay."""
    race = [r for r in rows if r["circuit"] == circuit and r["year"] == year]
    if not race:
        raise ValueError(f"No race for {circuit} {year} in the dataset")
    if any("safety_car" in r["exclusion_reasons"] for r in race) and not (windows or {}).get(race[0]["session_key"]):
        raise ValueError(f"{circuit} {year} had a safety car and no safety-car windows were given to replay it, "
                         "so real times can't be compared")
    return race


def driver_choices(rows: list[dict], circuit: str, year: int, model=None, min_clean_laps: int = 5,
                   windows: dict[int, list[dict]] | None = None) -> list[int]:
    '''
    Drivers whose race can be compared: same rules as backtest.backtest_race.

    rows: load_dataset rows
    circuit, year: a race from comparable_races
    model: fitted model; if given, a driver also needs at least min_clean_laps clean
        laps in the first half of the race, because that is where compare_driver
        takes the pace from (backtest.first_half_pace)
    windows: neutralisation.load_neutralisations result, needed for a race with a safety car

    returns: sorted driver numbers with a lap time on every lap 1..race
    distance (so lapped and retired drivers are left out) and, if model is None,
    at least one clean lap. With a model, a driver whose laps it can't predict (a
    compound it never saw at that circuit) is left out too, and so is one whose real strategy
    the simulator would refuse (e.g. two stints on the same compound).

    raises ValueError if the race isn't in rows, has no timed laps, or had a safety car with no windows given.
    '''
    race = _race_rows(rows, circuit, year, windows)
    distance = race_distance(race)
    if distance is None:
        raise ValueError(f"{circuit} {year} has no timed laps")
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
            try:
                ok = first_half_pace(by_driver[driver], model, distance, min_clean_laps) is not None
                if ok:              # the simulator refuses a real strategy that broke the two-compound rule
                    validate_strategy(actual_strategy([r for r in by_driver[driver] if r["lap_number"] <= distance]),
                                      distance)
            except ValueError:
                ok = False          # an unseen compound@circuit pair, or a real strategy the simulator refuses
        if ok:
            choices.append(driver)
    return sorted(choices)


def load_driver_names(path) -> dict[tuple[int, int], dict]:
    '''
    Driver names written by scripts/build_driver_names.py.

    path: data/processed/driver_names.json
    returns: dict (session_key, driver_number) -> {"acronym", "name", "team"}; {} if
    the file doesn't exist, so the app can fall back to car numbers.
    '''
    try:
        with open(path, encoding="utf-8") as f:
            table = json.load(f)
    except FileNotFoundError:
        return {}
    return {(int(session), int(number)): value
            for session, drivers in table.items() for number, value in drivers.items()}


def race_session_key(rows: list[dict], circuit: str, year: int) -> int:
    """The session_key of one race; raises ValueError if the race isn't in rows."""
    for row in rows:
        if row["circuit"] == circuit and row["year"] == year:
            return row["session_key"]
    raise ValueError(f"No race for {circuit} {year} in the dataset")


def compare_driver(rows: list[dict], inputs: dict, circuit: str, year: int, driver: int,
                   min_clean_laps: int = 5, custom: dict | None = None, traffic: bool = False,
                   light: bool = False) -> dict:
    '''
    One driver's real strategy against the candidate strategies (SPEC section 1).

    rows, inputs, circuit, year: as in race_settings; the race must have no safety car
    driver: driver number, one of driver_choices
    min_clean_laps: first-half clean laps needed to estimate the car's pace
    custom: optional custom_strategy result, added as "custom" to the strategies
    light: used by the refits: skip the checks and return only {"ranking": ...}
    traffic: if True, every strategy runs against the other cars' real lap start times
        (inputs["traffic_table"], traffic.traffic_timeline). The real strategy sits where
        it really was; an alternative moves through the field by how much faster or slower
        it is than the real strategy. The other cars don't react. The car's pace also has the
        traffic of its first half taken out.

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
        "refit_gaps": strategy name -> the gap to the real strategy (median pit loss, no wear offset)
            under each refit in inputs["ensemble"] that could simulate it; empty lists without an ensemble
        "neutralisation_windows": the race's safety-car windows (inputs["neutralisations"]);
            [] if none. When there are some, laps under them take the field's real lap time,
            a stop under a real safety car costs inputs["sc_pit_loss"]["ratio"] times the pit
            loss, and a "1stop_under_SC" candidate is added if the race had a real safety car.

    raises ValueError if the race had a safety car, the driver isn't in
    driver_choices (including too few clean first-half laps), or the simulator
    refuses the driver's real strategy.
    '''
    windows = inputs.get("neutralisations", {})
    race = _race_rows(rows, circuit, year, windows)
    if not light and driver not in driver_choices(rows, circuit, year, inputs["model"], min_clean_laps, windows):
        raise ValueError(f"Car {driver} didn't run every lap of {circuit} {year} with a time "
                         "(lapped, retired or missing data), so it can't be compared")
    settings = race_settings(rows, inputs, circuit, year)
    distance = settings["race_distance"]
    laps = sorted((r for r in race if r["driver_number"] == driver and r["lap_number"] <= distance),
                  key=lambda r: r["lap_number"])
    actual = actual_strategy(laps)
    traffic_inputs, penalties = None, None
    if traffic:
        if "traffic_table" not in inputs:
            raise ValueError("inputs has no traffic_table; build it with fit_inputs")
        table = inputs["traffic_table"]
        field = start_times(race)
        penalties = real_lap_penalties(driver, real_gaps(race), table, actual["pit_laps"], distance)
        traffic_inputs = {"table": table, "real_start": field.get(driver, {}), "anchor": "actual",
                          "field": {d: times for d, times in field.items() if d != driver}}
    settings["reference_lap"] = first_half_pace(laps, inputs["model"], distance, min_clean_laps, penalties)
    # Everyone starts the race on the set they started on; only later sets are a free choice.
    strategies = {"actual": actual}
    for name, candidate in candidate_strategies(distance).items():
        strategies[name] = with_start_ages(candidate, actual)
    race_windows = windows.get(race[0]["session_key"], [])
    neutralisation = None
    if race_windows:
        ratio = (inputs.get("sc_pit_loss") or {}).get("ratio")
        neutralisation = build_neutralisation(race, race_windows, ratio)
        under_sc = safety_car_candidate(race_windows, distance)
        if under_sc is not None:
            strategies["1stop_under_SC"] = with_start_ages(under_sc, actual)
    if custom is not None:
        validate_strategy(custom, distance)
        strategies["custom"] = with_start_ages(custom, actual)
    result = _compare_all(strategies, settings, circuit, inputs, "actual", traffic_inputs, neutralisation, light)
    if light:
        return {"ranking": result["ranking"]}
    refit_gaps: dict[str, list[float]] = {name: [] for name in strategies}
    for member in inputs.get("ensemble", []):
        try:
            refit = compare_driver(rows, member, circuit, year, driver, min_clean_laps, custom, traffic, light=True)
        except ValueError:
            continue            # this refit can't simulate the car's real strategy; leave it out
        for row in refit["ranking"]:
            if row["gap"] is not None:
                refit_gaps[row["strategy"]].append(row["gap"])
    actual_time = sum(r["lap_duration"] for r in laps)
    simulated = next(r["total"] for r in result["ranking"] if r["strategy"] == "actual")
    return {"settings": settings, "actual_strategy": actual, "actual_time": actual_time,
            "simulated_actual": simulated, "model_error": simulated - actual_time,
            "neutralisation_windows": race_windows, "strategies": strategies, **result,
            "refit_gaps": refit_gaps,
            "real_laps": pd.DataFrame({"lap_number": [r["lap_number"] for r in laps],
                                       "lap_time": [r["lap_duration"] for r in laps]})}
