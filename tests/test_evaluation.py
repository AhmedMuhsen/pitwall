import pytest
from pitwall.evaluation import score, split_by_year, score_by_group
import math
import pandas as pd

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
        result = score(actual, predicted)
    
def test_lists_diff_length():
    actual = [1.0, -1.0]
    predicted = [0.0, 0.0, 0.0]

    with pytest.raises(ValueError):
        result = score(actual, predicted)

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
    train, test = split_by_year(rows)

    assert len(train) == 4
    assert len(test) == 3
    assert all(r['year'] == 2024 for r in train)
    assert all(r['year'] == 2025 for r in test)


def test_failure_case():

    rows = [
        {'year': 2023}
    ]
    with pytest.raises(ValueError):
        train, test = split_by_year(rows)

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