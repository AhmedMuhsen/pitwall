from pitwall.model import PairAgeColumns, PooledWearModel, build_pipeline
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


def pooled_dataset():
    """HARD@X wears 0.05 s/lap and MEDIUM@X 0.15 s/lap over 40 laps each; HARD@Y is one wild lap."""
    rows = []
    for age in range(40):
        fraction = ((age * 7) % 40) / 40  # fuel not lined up with tyre age
        rows.append({"compound": "HARD", "circuit": "X", "tyre_age": age, "race_fraction": fraction,
                     "delta": 0.05 * age - 1.0 * fraction})
        rows.append({"compound": "MEDIUM", "circuit": "X", "tyre_age": age, "race_fraction": fraction,
                     "delta": 0.3 + 0.15 * age - 1.0 * fraction})
    rows.append({"compound": "HARD", "circuit": "Y", "tyre_age": 2, "race_fraction": 0.5, "delta": -3.0})
    return pd.DataFrame(rows)


def wear_rate(model, compound, circuit):
    """Predicted lap-time change per lap of tyre age for one pair, at fixed fuel."""
    laps = pd.DataFrame({"compound": [compound] * 2, "circuit": [circuit] * 2,
                         "tyre_age": [0, 10], "race_fraction": [0.5, 0.5]})
    young, old = model.predict(laps)
    return (old - young) / 10


def test_pooled_pair_with_many_laps_keeps_its_rate():
    data = pooled_dataset()
    model = PooledWearModel(alpha=100).fit(data, data["delta"])

    assert wear_rate(model, "MEDIUM", "X") == pytest.approx(0.15, abs=0.01)
    assert wear_rate(model, "HARD", "X") == pytest.approx(0.05, abs=0.01)


def test_pooled_pair_with_one_lap_stays_near_shared_rate():
    data = pooled_dataset()
    pooled = PooledWearModel(alpha=100).fit(data, data["delta"])
    unpooled = PooledWearModel(alpha=1e-6).fit(data, data["delta"])

    # With almost no penalty the single lap drags HARD@Y's adjustment far from 0.
    assert abs(unpooled.pair_adjustments()["HARD@Y"]) > 0.5
    assert abs(pooled.pair_adjustments()["HARD@Y"]) < 0.05


def test_pooled_huge_alpha_matches_shared_model():
    data = pooled_dataset()
    pooled = PooledWearModel(alpha=1e12).fit(data, data["delta"])
    shared = build_pipeline(True, False, "race_fraction").fit(data, data["delta"])

    assert pooled.predict(data) == pytest.approx(shared.predict(data), abs=1e-6)


def test_pooled_alpha_must_be_positive():
    data = pooled_dataset()
    with pytest.raises(ValueError, match="alpha"):
        PooledWearModel(alpha=0).fit(data, data["delta"])
