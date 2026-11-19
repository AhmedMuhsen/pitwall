import math

import pandas as pd
import pytest

from pitwall.evaluation import (
    leave_one_race_out,
    leave_one_year_out,
    score,
    score_by_group,
    split_by_year,
)


def test_score_zero_baseline():
    actual = [1.0, -1.0, 2.0]
    predicted = [0.0, 0.0, 0.0]

    result = score(actual, predicted)

    assert result['mae'] == pytest.approx(4/3)
    assert result['rmse'] == pytest.approx(math.sqrt(2))
    assert result['bias'] == pytest.approx(-2/3)

def test_score_empty_list():
    actual = []
    predicted = []
    
    with pytest.raises(ValueError):
        score(actual, predicted)
    
def test_lists_diff_length():
    actual = [1.0, -1.0]
    predicted = [0.0, 0.0, 0.0]

    with pytest.raises(ValueError):
        score(actual, predicted)

def test_normal_case():
    rows = [
        {'year': 2024},
        {'year': 2024},
        {'year': 2024},
        {'year': 2024},
        {'year': 2025},
        {'year': 2025},
        {'year': 2025},
    ]
    train, test = split_by_year(rows, [2024], [2025])

    assert len(train) == 4
    assert len(test) == 3
    assert all(r['year'] == 2024 for r in train)
    assert all(r['year'] == 2025 for r in test)


def test_failure_case():
    # Only 2023 rows, so the requested 2024 and 2025 have none.
    rows = [
        {'year': 2023}
    ]
    with pytest.raises(ValueError):
        train, test = split_by_year(rows, [2024], [2025])

def test_split_by_year_leaves_other_years_out():
    rows = [{'year': 2023}, {'year': 2024}, {'year': 2025}]
    train, test = split_by_year(rows, [2023], [2024])

    assert train == [{'year': 2023}]
    assert test == [{'year': 2024}]

def test_split_by_year_overlapping_years():
    rows = [{'year': 2023}, {'year': 2024}]
    with pytest.raises(ValueError):
        split_by_year(rows, [2023, 2024], [2024])

def test_leave_one_year_out_holds_out_each_year_once():
    rows = [
        {'year': 2023, 'lap_number': 1},
        {'year': 2024, 'lap_number': 1},
        {'year': 2024, 'lap_number': 2},
        {'year': 2025, 'lap_number': 1},
    ]
    splits = leave_one_year_out(rows, [2024, 2023])

    assert [year for year, _, _ in splits] == [2023, 2024]
    year, train, validation = splits[0]
    assert train == [{'year': 2024, 'lap_number': 1}, {'year': 2024, 'lap_number': 2}]
    assert validation == [{'year': 2023, 'lap_number': 1}]
    year, train, validation = splits[1]
    assert train == [{'year': 2023, 'lap_number': 1}]
    assert validation == [{'year': 2024, 'lap_number': 1}, {'year': 2024, 'lap_number': 2}]

def test_leave_one_year_out_needs_two_years():
    with pytest.raises(ValueError):
        leave_one_year_out([{'year': 2024}], [2024])

def test_score_by_group_scores_each_group():
    df = pd.DataFrame({
        "delta":     [0.0, 0.0, 0.0],
        "predicted": [1.0, -1.0, 2.0],
        "compound":  ["A", "A", "B"],
    })
    result = score_by_group(df, "compound")

    assert result.loc["A", "mae"] == pytest.approx(1)
    assert result.loc["A", "bias"] == pytest.approx(0)
    assert result.loc["A", "n"] == 2
    assert result.loc["B", "mae"] == pytest.approx(2)
    assert result.loc["B", "bias"] == pytest.approx(2)
    assert result.loc["B", "n"] == 1


def test_score_by_group_empty_dataframe():
    with pytest.raises(ValueError):
        score_by_group(pd.DataFrame(), "compound")

def test_leave_one_race_out_holds_out_each_race_once():
    rows = [
        {"session_key": 1, "lap_number": 1},
        {"session_key": 1, "lap_number": 2},
        {"session_key": 2, "lap_number": 1},
    ]
    splits = leave_one_race_out(rows)

    assert len(splits) == 2

    key, train, validation = splits[0]
    assert key == 1
    assert train == [{'session_key': 2, 'lap_number': 1}]
    assert validation == [{'session_key': 1, 'lap_number': 1}, {'session_key': 1, 'lap_number': 2}]

def test_leave_one_race_out_needs_two_races():
    rows = [{"session_key": 1, "lap_number": 1}]
    with pytest.raises(ValueError):
        leave_one_race_out(rows)