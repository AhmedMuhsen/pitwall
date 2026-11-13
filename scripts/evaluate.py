from pathlib import Path

import pyarrow.parquet as pq

from pitwall.evaluation import score, split_by_year
from pitwall.features import add_delta, driver_reference_laps

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


def main():
    rows = pq.read_table(DATASET_PATH).to_pylist()
    # Each race's reference comes from that race's own clean laps (DECISIONS 2026-11-12).
    rows = add_delta(rows, driver_reference_laps(rows))
    train, test = split_by_year(rows)
    print(f"train (2024): {len(train)} rows, test (2025): {len(test)} rows")

    print("\nZero baseline on 2025 test races")
    for flag in ("is_clean", "is_racing"):
        usable, skipped = scored_rows(test, flag)
        result = zero_baseline(usable)
        print(
            f"  {flag:<9}  n={len(usable):>5}  skipped (no delta)={skipped}  "
            f"MAE={result['mae']:.3f}s  RMSE={result['rmse']:.3f}s  bias={result['bias']:+.3f}s"
        )


if __name__ == "__main__":
    main()
