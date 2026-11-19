"""Builds data/processed/calibration.json: split-conformal interval half-widths (80%) for lap times, race totals
(races without and with a safety car) and strategy gaps between two real cars, and how well each held up.

Errors from 2023 and 2024 (each scored by a model fitted on the other year) are the calibration set. 2025 races, scored
by the final model, are the test: the intervals are first calibrated once on 2023/24 ("static") and then race by race
in date order ("rolling"). The half-width the app uses is calibrated on all of those errors.
Run after build_dataset.py and build_neutralisations.py:  uv run python scripts/build_calibration.py"""
import json
from pathlib import Path

import pandas as pd

import evaluate as ev
from pitwall.backtest import backtest_race, strategy_pair_errors
from pitwall.comparison import TRAIN_YEARS, comparable_races, fit_inputs, load_dataset
from pitwall.conformal import summarise_target
from pitwall.neutralisation import load_neutralisations

LEVEL = 0.8
TEST_YEAR = 2025
OUTPUT_PATH = Path("data/processed/calibration.json")


def race_order(rows):
    """(year, circuit) -> the race's first lap start, so races can be put in date order."""
    first = {}
    for row in rows:
        key = (row["year"], row["circuit"])
        if row["date_start"] is not None and (key not in first or row["date_start"] < first[key]):
            first[key] = row["date_start"]
    return first


def split_errors(records, order):
    """records: dicts with "year", "circuit" and "error". Returns (errors before TEST_YEAR, test errors per race in date order)."""
    calibration = [r["error"] for r in records if r["year"] < TEST_YEAR]
    by_race = {}
    for r in records:
        if r["year"] == TEST_YEAR:
            by_race.setdefault((r["year"], r["circuit"]), []).append(r["error"])
    return calibration, [by_race[key] for key in sorted(by_race, key=lambda k: order[k])]


def main():
    rows = load_dataset("data/processed/lap_dataset.parquet")
    windows = load_neutralisations("data/processed/neutralisations.json")
    order = race_order(rows)
    inputs = fit_inputs(rows, TRAIN_YEARS, windows)
    model = inputs["model"]
    targets = {}

    # Clean lap times (seconds): cross-year 2023/24, then 2025 laps of pairs the model knows.
    cross = ev.cross_year_predictions(True, False, rows, pooling_alpha=100_000)
    cross_records = [{"year": y, "circuit": c, "error": float(a - p)} for y, c, a, p in
                     zip(cross["year"], cross["circuit"], cross["delta"], cross["predicted"])]
    known = set(model.pair_adjustments())
    test = pd.DataFrame([r for r in rows if r["year"] == TEST_YEAR and r["is_clean"] and r["delta"] is not None
                         and f"{r['compound']}@{r['circuit']}" in known])
    test["error"] = test["delta"] - model.predict(test)
    lap_records = cross_records + test[["year", "circuit", "error"]].to_dict("records")
    targets["lap"] = summarise_target(*split_errors(lap_records, order), LEVEL)

    # Race totals, races without a safety car (seconds): first-half pace, traffic on.
    cross_totals = pd.DataFrame(ev.cross_year_backtest(rows, pooling_alpha=100_000, pace="first_half", traffic=True))
    records = cross_totals[cross_totals["predicted"].notna()][["year", "circuit", "error"]].to_dict("records")
    for year, circuit in sorted({(r["year"], r["circuit"]) for r in rows if r["year"] == TEST_YEAR}):
        race = [r for r in rows if r["year"] == year and r["circuit"] == circuit]
        if circuit not in inputs["pit_loss"] or any("safety_car" in r["exclusion_reasons"] for r in race):
            continue
        for record in backtest_race(race, model, inputs["pit_loss"][circuit]["median"],
                                    inputs["lap_one_loss"].get(circuit, inputs["lap_one_loss_default"]),
                                    inputs["max_ages"], "first_half", inputs["traffic_table"]):
            if record["predicted"] is not None:
                records.append({"year": year, "circuit": circuit, "error": record["error"]})
    targets["race_total"] = summarise_target(*split_errors(records, order), LEVEL)

    # Race totals, races with a safety car or virtual safety car: lap times replayed, cheaper stops under a real one.
    sc = pd.DataFrame(ev.safety_car_backtest(rows, windows))
    sc = sc[(sc["variant"] == "laps+stops") & sc["error"].notna()]
    targets["race_total_safety_car"] = summarise_target(*split_errors(sc[["year", "circuit", "error"]].to_dict("records"), order), LEVEL)

    # Gap between two real cars, second half of the race (seconds), traffic on. Races without a safety car only.
    races = comparable_races(rows)
    pairs = []
    from pitwall.analysis import max_clean_tyre_age, pit_loss_by_circuit, stop_losses
    from pitwall.comparison import fit_final_model
    from pitwall.evaluation import leave_one_year_out
    from pitwall.simulator import observed_max_ages
    from pitwall.traffic import fit_traffic_penalty
    for year, fold_train, _ in leave_one_year_out(rows, list(TRAIN_YEARS)):
        fold_model = fit_final_model(fold_train)
        years = sorted({r["year"] for r in fold_train})
        pairs += strategy_pair_errors(ev.second_half_records(
            rows, [r for r in races if r[0] == year], fold_model,
            pit_loss_by_circuit(stop_losses(fold_train, fold_model), years),
            observed_max_ages(max_clean_tyre_age(fold_train), years), fit_traffic_penalty(fold_train, fold_model)))
    pairs += strategy_pair_errors(ev.second_half_records(
        rows, [r for r in races if r[0] == TEST_YEAR], model, inputs["pit_loss"], inputs["max_ages"],
        inputs["traffic_table"]))
    targets["gap"] = summarise_target(*split_errors(pairs, order), LEVEL)

    result = {"level": LEVEL, "unit": "seconds", "test_year": TEST_YEAR, "calibration_years": list(TRAIN_YEARS),
              "targets": targets}
    OUTPUT_PATH.write_text(json.dumps(result, indent=1), encoding="utf-8")
    print(f"{'target':<24}{'n cal.':>8}{'n test':>8}{'half-width':>12}{'static cov.':>13}{'rolling cov.':>14}")
    for name, t in targets.items():
        print(f"{name:<24}{t['n_calibration'] - t['n_test']:>8}{t['n_test']:>8}{t['half_width']:>12.2f}"
              f"{t['static']['coverage']:>13.0%}{t['rolling']['coverage']:>14.0%}")
    print(f"wrote {OUTPUT_PATH} (nominal level {LEVEL:.0%}; test year {TEST_YEAR})")


if __name__ == "__main__":
    main()
