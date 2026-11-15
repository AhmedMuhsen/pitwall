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

def split_by_year(rows: list[dict]) -> (list[dict], list[dict]):
    '''
    Takes in race rows
    Splits by year (2024 -> train, 2025 -> test)
    Raises a ValueError if we get a race not in 2024 or 2025
    Returns train & test
    '''
    train = []
    test = []
    for r in rows:
        if r['year'] == 2024:
            train.append(r)
        elif r['year'] == 2025:
            test.append(r)
        else:
            raise ValueError(f'Unexpected race year: {r['year']}')
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