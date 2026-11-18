from pitwall.analysis import average_lap_time_by_tyre_age
from pitwall.analysis import max_clean_tyre_age
from pitwall.analysis import median_clean_lap_by_race_lap
from pitwall.analysis import lap_one_losses, pit_loss_by_circuit, residual_trends, stop_losses
import pytest

def test_empty_lap_raises():
    with pytest.raises(ValueError):
        average_lap_time_by_tyre_age([])

def test_none_lap_duration_is_ignored():
    laps = [
        {"tyre_age": 1, "lap_duration": 90.0},
        {"tyre_age": 1, "lap_duration": None},
    ]
    assert average_lap_time_by_tyre_age(laps) == {1: 90.0}
    
def test_normal_case():
    laps = [
        {"tyre_age": 1, "lap_duration": 90.0},
        {"tyre_age": 1, "lap_duration": 92.0},
        {"tyre_age": 4, "lap_duration": 93.0},
        {"tyre_age": 4, "lap_duration": 95.0},
    ]
    assert average_lap_time_by_tyre_age(laps) == {1: 91.0, 4: 94.0}

def test_all_ages_none():
    laps = [
        {"tyre_age": 1, "lap_duration": None},
        {"tyre_age": 1, "lap_duration": None},
        {"tyre_age": 4, "lap_duration": 93.0},
        {"tyre_age": 4, "lap_duration": 95.0},
    ]
    assert average_lap_time_by_tyre_age(laps) == {4: 94.0}

def test_two_clean_laps():
    rows = [
        {"circuit": 'Monza', "year" : 2024, "compound" : 'SOFT', 'is_clean': True, 'tyre_age' : 7},
        {"circuit": 'Monza', "year" : 2024, "compound" : 'SOFT', 'is_clean': True, 'tyre_age' : 3}
    ]

    result = max_clean_tyre_age(rows)

    assert result == {("Monza", 2024, "SOFT"): 7}

def test_one_unclean_laps():
    rows = [
        {"circuit": 'Monza', "year" : 2024, "compound" : 'SOFT', 'is_clean': True, 'tyre_age' : 3},
        {"circuit": 'Monza', "year" : 2024, "compound" : 'SOFT', 'is_clean': False, 'tyre_age' : 12}
    ]

    result = max_clean_tyre_age(rows)
    assert result == {("Monza", 2024, "SOFT"): 3}

def test_invalid_unclean_laps():
    rows = [
        {"circuit": 'Monza', "year" : 2024, "compound" : 'SOFT', 'is_clean': False, 'tyre_age' : 3},

    ]

    result = max_clean_tyre_age(rows)
    assert ("Monza", 2024, "SOFT") not in result

def test_two_years():
    rows = [
        {"circuit": 'Monza', "year" : 2024, "compound" : 'SOFT', 'is_clean': True, 'tyre_age' : 3},
        {"circuit": 'Monza', "year" : 2025, "compound" : 'SOFT', 'is_clean': True, 'tyre_age' : 3},

    ]

    result = max_clean_tyre_age(rows)
    assert ("Monza", 2024, "SOFT") in result
    assert ("Monza", 2025, "SOFT") in result

def test_median_by_race_lap():
    rows = [
        {"session_key": 1, "lap_number": 1, "lap_duration": 80.0, "is_clean": True},
        {"session_key": 1, "lap_number": 1, "lap_duration": 81.0, "is_clean": True},
        {"session_key": 1, "lap_number": 1, "lap_duration": 99.0, "is_clean": False},
        {"session_key": 1, "lap_number": 2, "lap_duration": 79.0, "is_clean": True},
        {"session_key": 1, "lap_number": 2, "lap_duration": 79.5, "is_clean": True},
        {"session_key": 1, "lap_number": 2, "lap_duration": 85.0, "is_clean": True},
        {"session_key": 2, "lap_number": 1, "lap_duration": 50.0, "is_clean": True},
    ]

    result = median_clean_lap_by_race_lap(rows, 1)
    assert result == {1: 80.5, 2: 79.5}

def test_median_by_race_lap_no_clean_laps():
    rows = [
        {"session_key": 1, "lap_number": 1, "lap_duration": 80.0, "is_clean": False},
    ]

    assert median_clean_lap_by_race_lap(rows, 1) == {}

def test_median_by_race_lap_empty_raises():
    with pytest.raises(ValueError):
        median_clean_lap_by_race_lap([], 1)



class StubModel:
    """delta = 0.1 * tyre_age + 1.0 * race_fraction."""

    def predict(self, X):
        return 0.1 * X["tyre_age"].to_numpy() + 1.0 * X["race_fraction"].to_numpy()


def stop_lap(driver, lap, compound, age, fraction, delta, reasons):
    return {"session_key": 1, "driver_number": driver, "lap_number": lap, "circuit": "X",
            "year": 2024, "compound": compound, "tyre_age": age, "race_fraction": fraction,
            "delta": delta, "exclusion_reasons": reasons}


def test_stop_losses_hand_example_and_skips():
    rows = [
        stop_lap(1, 9, "MEDIUM", 8, 0.18, 0.5, []),  # normal lap, not a stop
        # Measured stop: in-lap 3.0 - (0.9 + 0.2) = 1.9, out-lap 20.0 - (0.0 + 0.22) = 19.78 -> 21.68
        stop_lap(1, 10, "MEDIUM", 9, 0.20, 3.0, ["in_lap"]),
        stop_lap(1, 11, "HARD", 0, 0.22, 20.0, ["pit_out"]),
        # In-lap under the safety car
        stop_lap(2, 10, "MEDIUM", 9, 0.20, 3.0, ["in_lap", "safety_car"]),
        stop_lap(2, 11, "HARD", 0, 0.22, 20.0, ["pit_out"]),
        # Out-lap with no time
        stop_lap(3, 10, "MEDIUM", 9, 0.20, 3.0, ["in_lap"]),
        stop_lap(3, 11, "HARD", 0, 0.22, None, ["pit_out", "null_lap_duration"]),
        # In-lap with no out-lap row
        stop_lap(4, 10, "MEDIUM", 9, 0.20, 3.0, ["in_lap"]),
    ]

    result = {r["driver_number"]: r for r in stop_losses(rows, StubModel())}

    assert sorted(result) == [1, 2, 3, 4]
    assert result[1]["loss"] == pytest.approx(21.68)
    assert result[1]["skip_reason"] is None
    assert result[1]["in_lap"] == 10 and result[1]["circuit"] == "X" and result[1]["year"] == 2024
    assert (result[2]["loss"], result[2]["skip_reason"]) == (None, "safety_car")
    assert (result[3]["loss"], result[3]["skip_reason"]) == (None, "no_time")
    assert (result[4]["loss"], result[4]["skip_reason"]) == (None, "no_out_lap")


def test_stop_losses_no_stops_gives_empty_list():
    rows = [stop_lap(1, 9, "MEDIUM", 8, 0.18, 0.5, [])]

    assert stop_losses(rows, StubModel()) == []



def loss_record(circuit, year, loss, skip_reason=None):
    return {"circuit": circuit, "year": year, "loss": loss, "skip_reason": skip_reason}


def test_pit_loss_by_circuit_uses_chosen_years():
    losses = [
        loss_record("X", 2024, 20.0), loss_record("X", 2024, 22.0), loss_record("X", 2024, 30.0),
        loss_record("X", 2024, 21.0), loss_record("X", 2023, 25.0),
        loss_record("X", 2024, None, "safety_car"),
        loss_record("X", 2025, 99.0), loss_record("X", 2025, None, "no_time"),  # not a chosen year
    ]

    result = pit_loss_by_circuit(losses, years=[2023, 2024])

    # Measured 2023-2024: 20, 21, 22, 25, 30
    assert result == {"X": {"median": 22.0, "q25": 21.0, "q75": 25.0, "measured": 5,
                            "skipped": {"safety_car": 1}}}


def test_pit_loss_by_circuit_leaves_out_circuit_with_no_measured_stop():
    losses = [loss_record("X", 2024, 20.0), loss_record("Y", 2024, None, "safety_car")]

    result = pit_loss_by_circuit(losses, years=[2024])

    assert list(result) == ["X"]
    assert result["X"]["q25"] == result["X"]["q75"] == 20.0  # one stop: spread is that stop



def test_lap_one_losses_hand_example_and_skips():
    rows = [
        # Lap 1: 7.0 - (0.0 + 0.02) = 6.98
        stop_lap(1, 1, "MEDIUM", 0, 0.02, 7.0, ["lap_1"]),
        stop_lap(1, 2, "MEDIUM", 1, 0.04, 0.5, []),  # not lap 1
        stop_lap(2, 1, "MEDIUM", 0, 0.02, 9.0, ["lap_1", "safety_car"]),
        stop_lap(3, 1, "SOFT", 2, 0.02, None, ["lap_1", "null_lap_duration"]),
    ]

    result = {r["driver_number"]: r for r in lap_one_losses(rows, StubModel())}

    assert sorted(result) == [1, 2, 3]
    assert result[1]["loss"] == pytest.approx(6.98) and result[1]["skip_reason"] is None
    assert (result[2]["loss"], result[2]["skip_reason"]) == (None, "safety_car")
    assert (result[3]["loss"], result[3]["skip_reason"]) == (None, "no_time")
    assert result[1]["circuit"] == "X" and result[1]["year"] == 2024



class SoftOnlyModel(StubModel):
    """Like StubModel, but raises for any compound other than SOFT (as a model that never saw it)."""

    def predict(self, X):
        if (X["compound"] != "SOFT").any():
            raise ValueError("Pairs not seen in training")
        return super().predict(X)


def test_stop_losses_skips_stop_model_cannot_predict_and_keeps_others():
    rows = [
        stop_lap(1, 10, "SOFT", 9, 0.20, 3.0, ["in_lap"]),  # 3.0 - 1.1 = 1.9
        stop_lap(1, 11, "SOFT", 0, 0.22, 20.0, ["pit_out"]),  # 20.0 - 0.22 = 19.78
        stop_lap(2, 10, "SOFT", 9, 0.20, 3.0, ["in_lap"]),
        stop_lap(2, 11, "HARD", 0, 0.22, 20.0, ["pit_out"]),
    ]

    result = {r["driver_number"]: r for r in stop_losses(rows, SoftOnlyModel())}

    assert result[1]["loss"] == pytest.approx(21.68) and result[1]["skip_reason"] is None
    assert (result[2]["loss"], result[2]["skip_reason"]) == (None, "model_cannot_predict")


def test_lap_one_losses_skips_lap_model_cannot_predict():
    rows = [stop_lap(1, 1, "SOFT", 0, 0.02, 7.0, ["lap_1"]), stop_lap(2, 1, "HARD", 0, 0.02, 7.0, ["lap_1"])]

    result = {r["driver_number"]: r for r in lap_one_losses(rows, SoftOnlyModel())}

    assert result[1]["loss"] == pytest.approx(6.98)
    assert (result[2]["loss"], result[2]["skip_reason"]) == (None, "model_cannot_predict")


class ZeroModel:
    """Predicts a delta of 0, so the residual is the delta itself; refuses compounds in `unseen`."""

    def __init__(self, unseen=()):
        self.unseen = set(unseen)

    def predict(self, X):
        if set(X["compound"]) & self.unseen:
            raise ValueError("unseen compound")
        return [0.0] * len(X)


def trend_rows(delta):
    """20-lap race, two drivers with different pit laps and a used set, so race lap and tyre ages separate.
    delta(race_fraction, compound, tyre_age) gives each lap's delta."""
    rows = []
    stints = {1: [("SOFT", 1, 10, 0), ("HARD", 11, 20, 0)], 2: [("HARD", 1, 6, 0), ("SOFT", 7, 20, 5)]}
    for driver, driver_stints in stints.items():
        for compound, first, last, start_age in driver_stints:
            for lap in range(first, last + 1):
                age = start_age + lap - first
                rows.append({"session_key": 7, "circuit": "X", "year": 2024, "driver_number": driver,
                             "lap_number": lap, "compound": compound, "tyre_age": age,
                             "race_fraction": lap / 20, "is_clean": True,
                             "delta": delta(lap / 20, compound, age)})
    return rows


def test_residual_trends_finds_pure_race_lap_drift():
    rows = trend_rows(lambda frac, compound, age: 2.0 * frac)

    result = {r["compound"]: r for r in residual_trends(rows, ZeroModel(), min_laps=5)}

    for compound in ("SOFT", "HARD"):
        assert result[compound]["race_fraction_slope"] == pytest.approx(2.0)
        assert result[compound]["tyre_age_slope"] == pytest.approx(0.0, abs=1e-9)
        assert result[compound]["skip_reason"] is None
    assert result["SOFT"]["n_laps"] == 24 and result["HARD"]["n_laps"] == 16


def test_residual_trends_finds_wear_per_compound():
    rows = trend_rows(lambda frac, compound, age: 0.5 + (0.1 if compound == "SOFT" else 0.03) * age)

    result = {r["compound"]: r for r in residual_trends(rows, ZeroModel(), min_laps=5)}

    assert result["SOFT"]["tyre_age_slope"] == pytest.approx(0.1)
    assert result["HARD"]["tyre_age_slope"] == pytest.approx(0.03)
    assert result["SOFT"]["race_fraction_slope"] == pytest.approx(0.0, abs=1e-9)


def test_residual_trends_skips_small_and_unpredictable_compounds():
    rows = trend_rows(lambda frac, compound, age: 2.0 * frac)

    result = {r["compound"]: r for r in residual_trends(rows, ZeroModel(), min_laps=20)}
    assert result["HARD"]["skip_reason"] == "too_few_laps" and result["HARD"]["tyre_age_slope"] is None
    assert result["SOFT"]["skip_reason"] is None

    result = {r["compound"]: r for r in residual_trends(rows, ZeroModel(unseen=["SOFT", "HARD"]), min_laps=5)}
    assert result["SOFT"]["skip_reason"] == "model_cannot_predict"
    assert result["HARD"]["skip_reason"] == "model_cannot_predict"


def test_residual_trends_refuses_collinear_race():
    # One driver, one stint per compound, all new sets: race lap and tyre ages are tied together.
    rows = [r for r in trend_rows(lambda frac, compound, age: 2.0 * frac) if r["driver_number"] == 1]

    result = residual_trends(rows, ZeroModel(), min_laps=5)

    assert {r["skip_reason"] for r in result} == {"collinear"}
    assert all(r["race_fraction_slope"] is None for r in result)
