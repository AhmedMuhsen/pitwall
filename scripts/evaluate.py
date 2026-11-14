from pathlib import Path
import pandas as pd
import pyarrow.parquet as pq

from pitwall.evaluation import score, split_by_year
from pitwall.features import add_delta, driver_reference_laps
from pitwall.model import build_pipeline

DATASET_PATH = Path("data/processed/lap_dataset.parquet")


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

def fit_model(include_race_lap: bool, wear_by_pair: bool, train):
    usable_rows, _ = scored_rows(train, "is_clean")
    train_df = pd.DataFrame(usable_rows)

    pipeline = build_pipeline(include_race_lap, wear_by_pair)
    pipeline.fit(train_df, train_df['delta'])

    return pipeline

def training_pairs(train):
    """(compound, circuit) pairs on the 2024 clean laps the models are fitted on."""
    usable_rows, _ = scored_rows(train, "is_clean")
    return {(row["compound"], row["circuit"]) for row in usable_rows}

def main():
    rows = pq.read_table(DATASET_PATH).to_pylist()
    # Each race's reference comes from that race's own clean laps (DECISIONS 2026-11-12).
    rows = add_delta(rows, driver_reference_laps(rows))
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

if __name__ == "__main__":
    main()
