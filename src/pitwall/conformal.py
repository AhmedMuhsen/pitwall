"""Prediction intervals with measured coverage, by split conformal prediction.

An interval is the prediction plus or minus a half-width taken from how wrong the model was on data it hadn't seen
(a calibration set). It needs no assumption about the shape of the errors. The guarantee ("covers the truth at least
the stated share of the time") holds only if new errors look like the calibration errors, which a new season can
break, so coverage is always measured on later races (see rolling_coverage), never assumed.
"""
import json
import math


def conformal_half_width(errors: list[float], level: float = 0.8) -> float:
    '''
    Half-width of a split-conformal interval.

    errors: model errors (predicted minus actual, or the reverse) on held-out data, in any unit
    level: the share of future errors the interval should cover, strictly between 0 and 1

    returns: the k-th smallest absolute error, with k = ceil((n + 1) * level): the finite-sample correction that makes
    the coverage at least `level` when new errors are exchangeable with these.

    raises ValueError if level isn't between 0 and 1, or there are too few errors for that level (an honest interval
    would be infinite): at least level / (1 - level) are needed, e.g. 4 for 80%.
    '''
    if not 0 < level < 1:
        raise ValueError(f"level must be between 0 and 1, got {level}")
    n = len(errors)
    k = math.ceil((n + 1) * level)
    if k > n:
        raise ValueError(f"{n} calibration errors are too few for a {level:.0%} interval "
                         f"(need at least {math.ceil(level / (1 - level))})")
    return float(sorted(abs(e) for e in errors)[k - 1])


def coverage(errors: list[float], half_width: float) -> float:
    '''Share of errors whose absolute value is within half_width. Raises ValueError if errors is empty.'''
    if not errors:
        raise ValueError("No errors to measure coverage on")
    return sum(abs(e) <= half_width for e in errors) / len(errors)


def rolling_coverage(calibration: list[float], batches: list[list[float]], level: float = 0.8) -> dict:
    '''
    Coverage when the calibration set grows batch by batch, as it would while a season is run.

    calibration: errors known before the first batch (e.g. the previous seasons)
    batches: later errors in time order, one list per race; each batch is scored with a half-width calibrated on the
        calibration errors plus every earlier batch, then joins the calibration set
    level: as in conformal_half_width

    returns: dict with "batches" (one dict per non-empty batch: "half_width", "n", "covered"), "coverage" (share of all
    batch errors covered) and "mean_half_width" (average over the batch errors, in the error's unit).

    raises ValueError if there is no non-empty batch, or conformal_half_width does.
    '''
    seen = list(calibration)
    scored = []
    for batch in batches:
        if not batch:
            continue
        half_width = conformal_half_width(seen, level)
        scored.append({"half_width": half_width, "n": len(batch), "covered": sum(abs(e) <= half_width for e in batch)})
        seen.extend(batch)
    if not scored:
        raise ValueError("No batch to score")
    total = sum(b["n"] for b in scored)
    return {"batches": scored, "coverage": sum(b["covered"] for b in scored) / total,
            "mean_half_width": sum(b["half_width"] * b["n"] for b in scored) / total}


def summarise_target(calibration: list[float], batches: list[list[float]], level: float = 0.8) -> dict:
    '''
    The numbers that describe one interval and how well it held up.

    calibration, batches, level: as in rolling_coverage (the batches are the held-out test races, in time order)

    returns: dict with
        "level": the nominal level
        "half_width": calibrated on every error (calibration and test): the one the app uses
        "n_calibration": how many errors that is
        "static": {"half_width", "coverage"}: calibrated once on `calibration` only, coverage on all test errors
        "rolling": {"coverage", "mean_half_width"}: calibrated race by race (rolling_coverage)
        "n_test": number of test errors
    '''
    test = [e for batch in batches for e in batch]
    static_half_width = conformal_half_width(calibration, level)
    rolling = rolling_coverage(calibration, batches, level)
    return {"level": level, "half_width": conformal_half_width(calibration + test, level),
            "n_calibration": len(calibration) + len(test),
            "static": {"half_width": static_half_width, "coverage": coverage(test, static_half_width)},
            "rolling": {"coverage": rolling["coverage"], "mean_half_width": rolling["mean_half_width"]},
            "n_test": len(test)}


def load_calibration(path) -> dict | None:
    '''
    The interval half-widths written by scripts/build_calibration.py.

    path: data/processed/calibration.json
    returns: the parsed dict ("level", "unit", "test_year", "targets" -> summarise_target dicts), or None if the file
    doesn't exist, so the app can run without intervals.
    '''
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return None
