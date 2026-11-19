"""Fits the final model and the refit ensemble that the strategy comparison and its verdict are built on."""
import random
from statistics import median
from typing import Any

import pandas as pd
import pyarrow.parquet as pq

from pitwall.analysis import (
    lap_one_losses,
    max_clean_tyre_age,
    pit_loss_by_circuit,
    residual_trends,
    stop_losses,
)
from pitwall.evaluation import leave_one_year_out
from pitwall.features import add_delta, add_race_fraction, driver_reference_laps
from pitwall.model import PooledWearModel
from pitwall.neutralisation import (
    fit_sc_pit_loss,
)
from pitwall.simulator import observed_max_ages
from pitwall.traffic import (
    fit_traffic_penalty,
)

# The final model is fitted on 2023 and 2024; 2025 is the held-out test and is never used to choose or tune anything.
FINAL_ALPHA = 100_000


TRAIN_YEARS = [2023, 2024]


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
    # Each race's reference comes from that race's own clean laps.
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


def fit_inputs(rows: list[dict], train_years: list[int] = TRAIN_YEARS,
               windows: dict[int, list[dict]] | None = None, refits: int = 0) -> dict:
    '''
    Everything the comparison needs that is estimated from the training years.

    rows: load_dataset rows (any years; only train_years are used)
    train_years: years to fit on
    windows: neutralisation.load_neutralisations result (safety-car windows per session);
        without it races with a safety car can't be compared
    refits: if above 0, also fit that many refits on random 80% subsets of the races
        (fit_ensemble) and return them under "ensemble"

    returns: dict with
        "model": fit_final_model on train_years
        "pit_loss": analysis.pit_loss_by_circuit dict (median, q25, q75 per circuit)
        "lap_one_loss": dict circuit -> median lap-1 loss in seconds; a circuit whose lap 1 was under a
            safety car in every training race has none
        "lap_one_loss_default": the median over all circuits, used for such a circuit (as in the
            cross-year backtest)
        "traffic_table": traffic.fit_traffic_penalty on the training years
        "neutralisations": the windows given ({} if none)
        "sc_pit_loss": neutralisation.fit_sc_pit_loss on the training years (None if no
            stop was made under a real safety car in them)
        "max_ages": dict (circuit, compound) -> oldest clean tyre age
        "held_out_wear_errors": held_out_wear_errors over train_years
        "wear_range": 75th percentile of those errors (s per lap of age),
            the wear sensitivity range

    raises ValueError if fewer than two train_years (the wear range needs a
    held-out year) or a year has no rows.
    '''
    if len(train_years) < 2:
        raise ValueError(f"Need at least two training years for the wear range, got {train_years}")
    train = [r for r in rows if r["year"] in train_years]
    missing = set(train_years) - {r["year"] for r in train}
    if missing:
        raise ValueError(f"No rows for year(s): {sorted(missing)}")
    errors = held_out_wear_errors(rows, train_years)
    inputs = {**_fit_core(train, train_years, windows), "held_out_wear_errors": errors,
              "wear_range": float(pd.Series(errors).quantile(0.75))}
    if refits:
        inputs["ensemble"] = fit_ensemble(train, train_years, windows, inputs, refits)
    return inputs


def _fit_core(train: list[dict], train_years: list[int], windows: dict[int, list[dict]] | None) -> dict:
    """The parts of fit_inputs that are estimated from the rows (model, pit loss, lap-1 loss, observed
    tyre ages, traffic penalty, safety-car stop ratio); `train` holds only the training years."""
    model = fit_final_model(train)
    lap_one = pit_loss_by_circuit(lap_one_losses(train, model), train_years)
    pit_loss = pit_loss_by_circuit(stop_losses(train, model), train_years)
    lap_one_loss = {circuit: values["median"] for circuit, values in lap_one.items()}
    return {
        "model": model,
        "pit_loss": pit_loss,
        "lap_one_loss": lap_one_loss,
        "lap_one_loss_default": float(median(lap_one_loss.values())) if lap_one_loss else None,
        "max_ages": observed_max_ages(max_clean_tyre_age(train), train_years),
        "traffic_table": fit_traffic_penalty(train, model),
        "neutralisations": windows or {},
        "sc_pit_loss": fit_sc_pit_loss(train, windows, pit_loss, train_years) if windows else None,
    }


def fit_ensemble(train: list[dict], train_years: list[int], windows: dict[int, list[dict]] | None,
                 base: dict, size: int, share: float = 0.8, seed: int = 0) -> list[dict]:
    '''
    The same inputs refitted on different random subsets of the training races, to see how much a
    comparison depends on which races the model saw.

    train: load_dataset rows of the training years
    train_years, windows: as in fit_inputs
    base: the inputs fitted on all of `train`; a refit that lacks a circuit's pit loss or lap-1 loss
        takes it from here, and the observed tyre ages, windows and wear range are shared
    size: number of refits
    share: share of the races each refit is fitted on
    seed: random seed, so the same rows always give the same refits

    returns: a list of `size` inputs dicts (same keys as fit_inputs except "ensemble" and
    "held_out_wear_errors"). Every refit keeps all compound@circuit pairs the full model knows
    (a race is added back when a pair would otherwise be lost), so it can predict whatever the full
    model can.
    '''
    rng = random.Random(seed)
    sessions = sorted({r["session_key"] for r in train})
    pairs_by_session: dict[Any, set] = {}
    for row in train:
        if row["is_clean"] and row["delta"] is not None:
            pairs_by_session.setdefault(row["session_key"], set()).add((row["compound"], row["circuit"]))
    all_pairs = set().union(*pairs_by_session.values())
    members = []
    for _ in range(size):
        chosen = set(rng.sample(sessions, max(1, round(share * len(sessions)))))
        covered = set().union(*(pairs_by_session.get(sk, set()) for sk in chosen))
        for sk in rng.sample(sessions, len(sessions)):       # add races back until every pair is covered again
            if covered >= all_pairs:
                break
            if sk not in chosen and pairs_by_session.get(sk, set()) - covered:
                chosen.add(sk)
                covered |= pairs_by_session[sk]
        subset = [r for r in train if r["session_key"] in chosen]
        core = _fit_core(subset, train_years, windows)
        members.append({**base, **core,
                        "pit_loss": {**base["pit_loss"], **core["pit_loss"]},
                        "lap_one_loss": {**base["lap_one_loss"], **core["lap_one_loss"]},
                        "lap_one_loss_default": core["lap_one_loss_default"] or base["lap_one_loss_default"],
                        "max_ages": base["max_ages"], "sc_pit_loss": core["sc_pit_loss"] or base["sc_pit_loss"]})
        members[-1].pop("ensemble", None)
    return members
