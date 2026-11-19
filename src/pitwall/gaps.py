"""Reads a comparison: gap ranges over the sensitivity scenarios, the verdict, and the lap-by-lap gap."""
from typing import Any

import pandas as pd

# Final model and training years: DECISIONS 2026-11-17 and 2026-11-18.


# Median absolute error, in seconds, when a stint is predicted from the same car's other stints
# (scripts/evaluate.py print_stint_check; DECISIONS 2026-11-18). Re-measured on the 57-race 2023-2025 corpus: 5.3 s cross-year, 5.6 s on 2025.
STINT_ERROR_FLOOR = 5.3


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


def gap_ranges(sensitivity_rows: list[dict], baseline: str, base_pit_label: str = "median",
               refit_gaps: dict[str, list[float]] | None = None) -> list[dict]:
    '''
    For each strategy: its gap to the baseline at the best estimate, and how far
    that gap moves across the sensitivity scenarios.

    sensitivity_rows: sensitivity (or compare_race / compare_driver "sensitivity") rows
    baseline: the strategy the gaps are measured against
    base_pit_label: the pit-loss label of the best estimate (with wear offset 0)
    refit_gaps: compare_driver "refit_gaps"; if given, each strategy also gets the share of refits
        in which it is faster than the baseline

    returns: one dict per strategy the simulator accepted, smallest gap first, with
    "strategy", "gap" (best estimate, seconds; negative = faster than the baseline),
    "min_gap" and "max_gap" (over every scenario), "flagged" (any stint beyond the
    observed tyre ages), "p_faster" (share of refits with a gap below 0, None without refits),
    "refits" (how many refits simulated it) and "confidence": "baseline", "faster in every scenario"
    (max_gap < 0), "slower in every scenario" (min_gap > 0) or "depends on assumptions".

    raises ValueError if no row is the best-estimate scenario.
    '''
    by_strategy: dict[str, Any] = {}
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
        refits = (refit_gaps or {}).get(entry["strategy"], [])
        entry["refits"] = len(refits)
        entry["p_faster"] = sum(g < 0 for g in refits) / len(refits) if refits else None
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


def verdict(ranges: list[dict], floor: float = STINT_ERROR_FLOOR, strong: float = 0.9, lean: float = 0.7) -> dict:
    '''
    The one-line answer: does the model prefer an alternative to the baseline, and is that
    robust to which races it was fitted on?

    ranges: gap_ranges result. Flagged alternatives (tyre ages beyond anything observed) are
        never the answer: their totals are extrapolations.
    floor: seconds. A gap smaller than the model's typical error on one stint (the median
        absolute stint-total error when each stint is predicted from the same car's other stints,
        STINT_ERROR_FLOOR) can't be told from noise.
    strong, lean: the share of refits (the model fitted again on random 80% subsets of the training
        races) in which the alternative must be faster. Without refits (p_faster None) it is
        counted as `strong` if faster in every pit-loss/wear scenario, else as `lean`.

    returns: dict with "kind", "strategy" (the best alternative, or None), "range" (its gap_ranges
    entry, or None) and "robust" (it is faster in every pit-loss/wear scenario). "kind" is:
        "agrees": no unflagged alternative is faster at the best estimate
        "too_close": the best alternative is faster by less than `floor`, or in fewer than `lean` of refits
        "leans": faster by `floor` or more, and in `lean` to `strong` of refits
        "prefers": faster by `floor` or more, and in `strong` or more of refits
    '''
    alternatives = [r for r in ranges if r["confidence"] != "baseline" and not r["flagged"]]
    best = min(alternatives, key=lambda r: r["gap"], default=None)
    if best is None or best["gap"] >= 0:
        return {"kind": "agrees", "strategy": None, "range": None, "robust": False}
    p = best["p_faster"]
    if p is None:
        p = strong if best["confidence"] == "faster in every scenario" else lean
    if -best["gap"] < floor or p < lean:
        kind = "too_close"
    else:
        kind = "prefers" if p >= strong else "leans"
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
