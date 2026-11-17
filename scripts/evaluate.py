from pathlib import Path
import pandas as pd
import pyarrow.parquet as pq

from pitwall.evaluation import leave_one_race_out, score, score_by_group, split_by_year
from pitwall.features import add_delta, add_race_fraction, driver_reference_laps
from pitwall.model import build_pipeline

DATASET_PATH = Path("data/processed/lap_dataset.parquet")
# Tyre-age buckets for the error slices: 0-9, 10-19, 20-29, 30+ laps.
AGE_BINS = [-1, 9, 19, 29, float("inf")]
AGE_LABELS = ["0-9", "10-19", "20-29", "30+"]

LAP_BINS = [0, 10, 20, 30, 40, 50, 60, 70]
LAP_LABELS = ["1-10", "11-20", "21-30", "31-40", "41-50", "51-60", "61-70"]

def scored_rows(rows, flag):
    """Rows where `flag` is true, split into (usable, skipped) by whether delta exists."""
    selected = [row for row in rows if row[flag]]
    usable = [row for row in selected if row["delta"] is not None]
    return usable, len(selected) - len(usable)


def zero_baseline(rows):
    """Scores for predicting a delta of 0 on every row."""
    actual = [row["delta"] for row in rows]
    predicted = [0.0] * len(actual)
    return score(actual, predicted)

def fit_model(include_race_lap: bool, wear_by_pair: bool, train, fuel_column="lap_number"):
    usable_rows, _ = scored_rows(train, "is_clean")
    train_df = pd.DataFrame(usable_rows)

    pipeline = build_pipeline(include_race_lap, wear_by_pair, fuel_column)
    pipeline.fit(train_df, train_df['delta'])

    return pipeline

def training_pairs(train):
    """(compound, circuit) pairs on the 2024 clean laps the models are fitted on."""
    usable_rows, _ = scored_rows(train, "is_clean")
    return {(row["compound"], row["circuit"]) for row in usable_rows}    

def print_slices(train, test):
    """Error slices on 2025 clean laps, Model B next to Model C."""
    usable, _ = scored_rows(test, "is_clean")
    test_df = pd.DataFrame(usable)
    test_df["age_bucket"] = pd.cut(test_df["tyre_age"], bins=AGE_BINS, labels=AGE_LABELS)

    models = {"B": fit_model(True, False, train), "C": fit_model(True, True, train)}
    for by in ("compound", "circuit", "age_bucket"):
        tables = []
        for name, pipeline in models.items():
            scored = test_df.assign(predicted=pipeline.predict(test_df))
            tables.append(score_by_group(scored, by)[["mae", "bias"]].add_prefix(f"{name}_"))
        table = pd.concat(tables, axis=1)
        table["n"] = test_df.groupby(by, observed=True).size()
        print(f"\nClean 2025 laps by {by} (seconds)")
        print(table.round(3).to_string())


def held_out_predictions(include_race_lap, train, fuel_column="lap_number"):
    """Clean 2024 laps, each predicted by a model fitted on the other four 2024 races."""
    frames = []
    for _, fold_train, fold_validation in leave_one_race_out(train):
        pipeline = fit_model(include_race_lap, False, fold_train, fuel_column)
        usable, _ = scored_rows(fold_validation, "is_clean")
        validation_df = pd.DataFrame(usable)
        frames.append(validation_df.assign(predicted=pipeline.predict(validation_df)))
    return pd.concat(frames, ignore_index=True)


def print_held_out_2024(train):
    """Models on held-out 2024 races: overall, then B (fuel by lap) vs B_frac (fuel by race fraction)."""
    print("\nHeld-out 2024 races (fit on the other four), clean laps")
    results = {}
    models = (("A", False, "lap_number"), ("B", True, "lap_number"), ("B_frac", True, "race_fraction"))
    for name, include_race_lap, fuel_column in models:
        df = held_out_predictions(include_race_lap, train, fuel_column)
        df["age_bucket"] = pd.cut(df["tyre_age"], bins=AGE_BINS, labels=AGE_LABELS)
        df["lap_bucket"] = pd.cut(df["lap_number"], bins=LAP_BINS, labels=LAP_LABELS)
        result = score(df["delta"].tolist(), df["predicted"].tolist())
        print(
            f"  {name:<6}  n={len(df):>5}  "
            f"MAE={result['mae']:.3f}s  RMSE={result['rmse']:.3f}s  bias={result['bias']:+.3f}s"
        )
        results[name] = df

    for by in ("age_bucket", "lap_bucket"):
        tables = [score_by_group(results[name], by)[["mae", "bias"]].add_prefix(f"{name}_")
                  for name in ("B", "B_frac")]
        table = pd.concat(tables, axis=1)
        table["n"] = results["B"].groupby(by, observed=True).size()
        print(f"\nHeld-out 2024 by {by} (seconds)")
        print(table.round(3).to_string())

    for name in ("B", "B_frac"):
        df = results[name].assign(error=results[name]["predicted"] - results[name]["delta"])
        drift = df.pivot_table(index="lap_bucket", columns="circuit", values="error",
                               aggfunc="mean", observed=True)
        print(f"\nHeld-out 2024, Model {name} bias by lap_bucket and circuit (seconds)")
        print(drift.round(2).to_string())


def main():
    rows = pq.read_table(DATASET_PATH).to_pylist()
    # Each race's reference comes from that race's own clean laps (DECISIONS 2026-11-12).
    rows = add_delta(rows, driver_reference_laps(rows))
    rows = add_race_fraction(rows)
    # 2023 is for cross-year validation of per-circuit wear and isn't used here yet.
    rows = [row for row in rows if row["year"] != 2023]
    train, test = split_by_year(rows)
    print(f"train (2024): {len(train)} rows, test (2025): {len(test)} rows")

    # No 2024 wear rate exists for these pairs, so every model skips them (DECISIONS 2026-11-13).
    pairs = training_pairs(train)
    unseen = [row for row in test if (row["compound"], row["circuit"]) not in pairs]
    test = [row for row in test if (row["compound"], row["circuit"]) in pairs]
    print(f"left out of 2025 scoring, pair not in 2024 training: {len(unseen)} rows")

    print("\nZero baseline on 2025 test races")
    for flag in ("is_clean", "is_racing"):
        usable, skipped = scored_rows(test, flag)
        result = zero_baseline(usable)
        print(
            f"  {flag:<9}  n={len(usable):>5}  skipped (no delta)={skipped}  "
            f"MAE={result['mae']:.3f}s  RMSE={result['rmse']:.3f}s  bias={result['bias']:+.3f}s"
        )

    for include_race_lap, wear_by_pair in [(False, False), (True, False), (True, True)]:
        pipeline = fit_model(include_race_lap, wear_by_pair, train)
        print(f"\nLinear model, include_race_lap = {include_race_lap}, wear_by_pair = {wear_by_pair}, on 2025 test races")
        for flag in ("is_clean", "is_racing"):
            usable, skipped = scored_rows(test, flag)
            test_df = pd.DataFrame(usable)
            predicted = pipeline.predict(test_df).tolist()
            actual = test_df['delta'].tolist()
            result = score(actual, predicted)
            print(
                f"  {flag:<9}  n={len(usable):>5}  skipped (no delta)={skipped}  "
                f"MAE={result['mae']:.3f}s  RMSE={result['rmse']:.3f}s  bias={result['bias']:+.3f}s"
            )

    print_slices(train, test)
    print_held_out_2024(train)


if __name__ == "__main__":
    main()
