from pitwall.model import PairAgeColumns, build_pipeline
import pytest
import pandas as pd

def test_learns_linear_wear_rate():
    dataset = pd.DataFrame({"compound": ['SOFT', 'SOFT', 'SOFT', 'SOFT'], "tyre_age": [1, 3, 0, 4],
                            "delta": [0.1, 0.3, 0.0, 0.4]
    })

    pipeline = build_pipeline(False)
    pipeline.fit(dataset, dataset['delta'])
    new_lap = pd.DataFrame({"compound": ["SOFT"], "tyre_age": [10]})
    prediction = pipeline.predict(new_lap)

    assert prediction[0] == pytest.approx(1.0)

def test_include_race_lap_flag():
    dataset = pd.DataFrame({"compound": ['SOFT', 'SOFT', 'SOFT', 'SOFT'], "tyre_age": [1, 3, 0, 4],
                            "delta": [0.1, 0.3, 0.0, 0.4]
    })

    with pytest.raises(ValueError, match ='lap_number'):
        pipeline = build_pipeline(True)
        pipeline.fit(dataset, dataset['delta'])


def test_pair_age_columns_step_reuses_training_pairs():
    train = pd.DataFrame({"compound": ["SOFT", "HARD"], "circuit": ["Sakhir", "Monza"],
                          "tyre_age": [8, 15]})
    test = pd.DataFrame({"compound": ["HARD"], "circuit": ["Monza"], "tyre_age": [3]})

    step = PairAgeColumns().fit(train)
    result = step.transform(test)

    assert list(result.columns) == ["age:HARD@Monza", "age:SOFT@Sakhir"]
    assert result.iloc[0].tolist() == [3, 0]


def test_pair_age_columns_step_raises_on_pair_not_in_training():
    train = pd.DataFrame({"compound": ["SOFT"], "circuit": ["Sakhir"], "tyre_age": [8]})
    test = pd.DataFrame({"compound": ["MEDIUM"], "circuit": ["Sakhir"], "tyre_age": [5]})

    step = PairAgeColumns().fit(train)
    with pytest.raises(ValueError, match="MEDIUM@Sakhir"):
        step.transform(test)
