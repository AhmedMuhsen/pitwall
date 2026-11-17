import math
import pandas as pd

def score(actual: list[float], predicted: list[float]) -> dict[str, float]:
    '''
    Error scores of predicted deltas against actual deltas, in seconds.

    actual, predicted: lists of floats (seconds), same length, paired by
        position (predicted[i] is the prediction for actual[i])

    returns: dict with "mae" (mean absolute error), "rmse" (root mean
        squared error) and "bias" (mean error). Error is predicted minus
        actual, so a positive bias means the predictions are too slow.

    raises ValueError if either list is empty or the lengths differ.
    '''
    if not actual or not predicted:
        raise ValueError('List is empty')
    if len(actual) != len(predicted):
        raise ValueError('Lists have different lengths')
    errors = [p - a for p, a in zip(predicted, actual)]
    mae = sum(abs(e) for e in errors) / len(errors)
    rmse = math.sqrt(sum(e ** 2 for e in errors)/ len(errors))
    bias = sum(errors) / len(errors)
    return {'mae': mae, 'rmse': rmse, 'bias': bias}

def score_by_group(df: pd.DataFrame, by: str) -> pd.DataFrame:
    '''
    score for each group of rows, e.g. per compound or per circuit.

    df: DataFrame with "delta" (actual, seconds), "predicted" (seconds) and
        the column named by `by`
    by: name of the column to group on

    returns: DataFrame with one row per group (indexed by the group label)
        and columns "mae", "rmse", "bias" (seconds, as in score) and "n"
        (rows in that group). A group with small n can show a large error
        that means little.

    raises ValueError if df is empty.
    '''
    if df.empty:
        raise ValueError("DataFrame is empty")
    
    def group_scores(g):
        result = score(g['delta'].tolist(), g['predicted'].tolist())
        result["n"] = len(g)
        return pd.Series(result)
    return df.groupby(by).apply(group_scores)

def split_by_year(rows: list[dict], train_years: list[int], test_years: list[int]) -> tuple[list[dict], list[dict]]:
    '''
    Splits rows into train and test by race year.

    rows: list of dicts (dataset rows), each with "year" (int)
    train_years, test_years: years for each side, e.g. [2024] and [2025] for
        the test split, or [2023] and [2024] for cross-year validation

    returns: (train_rows, test_rows). Rows from any other year are left out, so
        a validation split on [2023] and [2024] can never contain 2025.

    raises ValueError if the two year lists overlap or either is empty, or if a
    requested year has no rows (a missing race would otherwise go unnoticed).
    '''
    if not train_years or not test_years:
        raise ValueError("train_years and test_years must both name at least one year")
    overlap = set(train_years) & set(test_years)
    if overlap:
        raise ValueError(f"Years in both train and test: {sorted(overlap)}")
    missing = (set(train_years) | set(test_years)) - {r['year'] for r in rows}
    if missing:
        raise ValueError(f"No rows for year(s): {sorted(missing)}")

    train = [r for r in rows if r['year'] in train_years]
    test = [r for r in rows if r['year'] in test_years]
    return train, test

def leave_one_race_out(rows: list[dict]) -> list[tuple[int, list[dict], list[dict]]]:
    '''
    One (train, validation) split per race, holding that race out.

    rows: list of dicts (dataset rows), each with "session_key" (int)

    returns: list of (session_key, train_rows, validation_rows), one per race
        in sorted session_key order. validation_rows are that race's rows and
        train_rows are every other race's rows, so no race is in both.

    raises ValueError if rows is empty or covers fewer than 2 races.
    '''
    if not rows:
        raise ValueError("Rows list is empty")
    session_keys = sorted({row['session_key'] for row in rows})
    if len(session_keys) < 2:
        raise ValueError(f'Need at least 2 races, got {len(session_keys)}')
    
    splits = []
    for key in session_keys:
        validation = [row for row in rows if row['session_key'] == key]
        train = [row for row in rows if row['session_key'] != key]
        splits.append((key, train, validation))
    return splits

def leave_one_year_out(rows: list[dict], years: list[int]) -> list[tuple[int, list[dict], list[dict]]]:
    '''
    One (train, validation) split per year, holding that year out.

    Every circuit appears once per year, so unlike leave_one_race_out the
    validation races' circuits are also in training, in another year. This is
    what lets per-circuit wear (Model C) be scored.

    rows: list of dicts (dataset rows), each with "year" (int)
    years: the years to use, e.g. [2023, 2024]. Rows from other years (2025,
        the test set) are left out of every split.

    returns: list of (validation_year, train_rows, validation_rows), one per
        year in sorted order. train_rows are the other years' rows.

    raises ValueError if fewer than 2 years are given, or a year has no rows
    (see split_by_year).
    '''
    years = sorted(set(years))
    if len(years) < 2:
        raise ValueError(f'Need at least 2 years, got {years}')

    splits = []
    for year in years:
        others = [y for y in years if y != year]
        train, validation = split_by_year(rows, others, [year])
        splits.append((year, train, validation))
    return splits