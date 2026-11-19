import pandas as pd
import pytest

from pitwall.neutralisation import (apply_neutralisation, build_neutralisation, field_lap_times, fit_sc_pit_loss,
                                    load_neutralisations, neutralised_windows)


def message(text, lap, date, category="SafetyCar"):
    return {"category": category, "message": text, "lap_number": lap, "date": date}


def test_neutralised_windows_pairs_starts_and_ends_by_kind():
    control = [  # deliberately out of order, with an unrelated message and a stewards' note
        message("VIRTUAL SAFETY CAR ENDING", 45, "2024-01-01T13:21:29+00:00"),
        message("SAFETY CAR IN THIS LAP", 22, "2024-01-01T12:41:01+00:00"),
        message("SAFETY CAR DEPLOYED", 20, "2024-01-01T12:36:41+00:00"),
        message("VIRTUAL SAFETY CAR DEPLOYED", 44, "2024-01-01T13:18:06+00:00"),
        message("TURN 4 INCIDENT - SAFETY CAR INFRINGEMENT", 41, "2024-01-01T13:00:00+00:00", category="Other"),
        message("DRS ENABLED", 3, "2024-01-01T12:10:00+00:00", category="Drs"),
    ]

    assert neutralised_windows(control) == [{"kind": "SC", "start": 20, "end": 22},
                                            {"kind": "VSC", "start": 44, "end": 45}]
    assert neutralised_windows([]) == []


def test_neutralised_windows_rejects_unmatched_or_incomplete_messages():
    with pytest.raises(ValueError, match="never deployed"):
        neutralised_windows([message("SAFETY CAR IN THIS LAP", 5, "2024-01-01T12:00:00+00:00")])
    with pytest.raises(ValueError, match="no end message"):
        neutralised_windows([message("VIRTUAL SAFETY CAR DEPLOYED", 5, "2024-01-01T12:00:00+00:00")])
    with pytest.raises(ValueError, match="no lap number"):
        neutralised_windows([message("SAFETY CAR DEPLOYED", None, "2024-01-01T12:00:00+00:00")])
    with pytest.raises(ValueError, match="already out"):
        neutralised_windows([message("SAFETY CAR DEPLOYED", 5, "2024-01-01T12:00:00+00:00"),
                             message("SAFETY CAR DEPLOYED", 6, "2024-01-01T12:01:00+00:00")])


def test_load_neutralisations(tmp_path):
    path = tmp_path / "windows.json"
    path.write_text('{"9165": [{"kind": "SC", "start": 20, "end": 22}], "9166": []}')

    assert load_neutralisations(path) == {9165: [{"kind": "SC", "start": 20, "end": 22}], 9166: []}
    assert load_neutralisations(tmp_path / "missing.json") == {}


def lap(driver, number, duration, in_lap=False, out_lap=False, session=1, year=2024, circuit="X"):
    return {"session_key": session, "year": year, "circuit": circuit, "driver_number": driver,
            "lap_number": number, "lap_duration": duration, "is_pit_out_lap": out_lap,
            "exclusion_reasons": ["in_lap"] if in_lap else []}


def test_field_lap_times_skips_pit_laps_and_missing_times():
    rows = [lap(1, 5, 130.0), lap(2, 5, 120.0), lap(3, 5, 500.0, in_lap=True), lap(4, 5, 400.0, out_lap=True),
            lap(5, 5, None), lap(1, 6, 100.0)]

    assert field_lap_times(rows) == {5: 125.0, 6: 100.0}


def test_build_neutralisation_hand_example():
    rows = [lap(1, 5, 130.0), lap(2, 5, 120.0), lap(1, 6, 100.0), lap(2, 6, 110.0), lap(1, 7, 90.0)]
    windows = [{"kind": "SC", "start": 5, "end": 5}, {"kind": "VSC", "start": 6, "end": 6}]

    result = build_neutralisation(rows, windows, 0.7, min_cars=1)

    assert result == {"lap_times": {5: 125.0, 6: 105.0}, "sc_laps": {5}, "laps": {5, 6},
                      "no_traffic_laps": {4, 5, 6, 7}, "pit_loss_ratio": 0.7}
    with pytest.raises(ValueError, match="neutralised laps"):
        build_neutralisation(rows, [{"kind": "SC", "start": 8, "end": 8}], None, min_cars=1)


def test_apply_neutralisation_replaces_laps_and_discounts_only_stops_under_a_real_safety_car():
    laps = pd.DataFrame({"lap_number": [1, 2, 3, 4], "lap_time": [90.0, 90.0, 90.0, 90.0]})
    neutral = {"lap_times": {2: 125.0, 3: 105.0}, "sc_laps": {2}, "laps": {2, 3}, "pit_loss_ratio": 0.7}

    new_laps, stop_loss = apply_neutralisation(laps, [2, 3], 20.0, neutral)

    assert new_laps["lap_time"].tolist() == [90.0, 125.0, 105.0, 90.0]
    assert stop_loss == {2: pytest.approx(14.0), 3: 20.0}       # lap 3 is under a VSC: normal cost
    assert laps["lap_time"].tolist() == [90.0] * 4              # the input is not changed

    unchanged, normal = apply_neutralisation(laps, [2], 20.0, None)
    assert unchanged is laps and normal == {2: 20.0}
    _, no_ratio = apply_neutralisation(laps, [2], 20.0, {**neutral, "pit_loss_ratio": None})
    assert no_ratio == {2: 20.0}


def test_fit_sc_pit_loss_hand_example():
    # Safety car on laps 5-6. Cars 3 and 4 stay out: the field runs 130 s on lap 5, 120 s on lap 6, 100 s on lap 7.
    rows = []
    for car in (3, 4):
        rows += [lap(car, 5, 130.0), lap(car, 6, 120.0), lap(car, 7, 100.0)]
    # Car 1 pits on lap 5: in-lap 140, out-lap 125 -> 140 + 125 - 130 - 120 = 15 s, 15 / 20 = 0.75 of the normal loss.
    rows += [lap(1, 5, 140.0, in_lap=True), lap(1, 6, 125.0, out_lap=True)]
    # Car 2 pits on lap 6: in-lap 132, out-lap 108 -> 132 + 108 - 120 - 100 = 20 s, ratio 1.0.
    rows += [lap(2, 6, 132.0, in_lap=True), lap(2, 7, 108.0, out_lap=True)]
    windows = {1: [{"kind": "SC", "start": 5, "end": 6}]}

    result = fit_sc_pit_loss(rows, windows, {"X": {"median": 20.0}}, [2024], min_cars=2)

    assert result == {"ratio": pytest.approx(0.875), "q25": pytest.approx(0.8125), "q75": pytest.approx(0.9375), "n": 2}


def test_fit_sc_pit_loss_returns_none_without_stops_under_a_real_safety_car():
    rows = [lap(1, 5, 140.0, in_lap=True), lap(1, 6, 125.0, out_lap=True), lap(3, 5, 130.0), lap(3, 6, 120.0)]

    assert fit_sc_pit_loss(rows, {1: [{"kind": "VSC", "start": 5, "end": 6}]}, {"X": {"median": 20.0}}, [2024]) is None
    assert fit_sc_pit_loss(rows, {1: [{"kind": "SC", "start": 5, "end": 6}]}, {"X": {"median": 20.0}}, [2023]) is None
    assert fit_sc_pit_loss(rows, {1: [{"kind": "SC", "start": 5, "end": 6}]}, {}, [2024]) is None


def test_neutralised_windows_a_race_that_finishes_under_the_safety_car_ends_on_the_chequered_flag():
    control = [message("SAFETY CAR DEPLOYED", 67, "2024-01-01T13:00:00+00:00"),
               {"category": "Flag", "flag": "CHEQUERED", "message": "CHEQUERED FLAG", "lap_number": 70,
                "date": "2024-01-01T13:10:00+00:00"}]

    assert neutralised_windows(control) == [{"kind": "SC", "start": 67, "end": 70}]
    with pytest.raises(ValueError, match="no end message"):
        neutralised_windows(control[:1])      # no chequered flag in the data: still refused


def test_neutralised_windows_a_virtual_safety_car_upgraded_to_a_safety_car_ends_there():
    control = [message("VIRTUAL SAFETY CAR DEPLOYED", 22, "2024-01-01T07:39:16+00:00"),
               message("SAFETY CAR DEPLOYED", 23, "2024-01-01T07:43:21+00:00"),
               message("SAFETY CAR IN THIS LAP", 26, "2024-01-01T07:49:36+00:00"),
               message("SAFETY CAR DEPLOYED", 27, "2024-01-01T07:53:02+00:00"),
               message("SAFETY CAR THROUGH THE PIT LANE", 28, "2024-01-01T07:55:00+00:00"),
               message("SAFETY CAR IN THIS LAP", 31, "2024-01-01T08:00:59+00:00"),
               {"category": "Flag", "flag": "CHEQUERED", "message": "CHEQUERED FLAG", "lap_number": 56,
                "date": "2024-01-01T08:30:00+00:00"}]

    assert neutralised_windows(control) == [{"kind": "VSC", "start": 22, "end": 23},
                                            {"kind": "SC", "start": 23, "end": 26},
                                            {"kind": "SC", "start": 27, "end": 31}]


def test_a_lap_needs_enough_cars_for_a_field_lap_time():
    # Lap 5: cars 1 and 2 on plain laps, car 3 on its in-lap. Lap 6: only car 1 on a plain lap.
    rows = [lap(1, 5, 130.0), lap(2, 5, 120.0), lap(3, 5, 500.0, in_lap=True), lap(1, 6, 100.0)]

    assert field_lap_times(rows) == {5: 125.0, 6: 100.0}
    assert field_lap_times(rows, min_cars=2) == {5: 125.0}
    with pytest.raises(ValueError, match="neutralised laps"):
        build_neutralisation(rows, [{"kind": "SC", "start": 5, "end": 6}], None)       # default min_cars is 3


def test_fit_sc_pit_loss_ignores_stops_on_laps_with_too_few_cars_for_a_field_time():
    rows = [lap(3, 5, 130.0), lap(3, 6, 120.0), lap(1, 5, 140.0, in_lap=True), lap(1, 6, 125.0, out_lap=True)]
    windows = {1: [{"kind": "SC", "start": 5, "end": 6}]}

    assert fit_sc_pit_loss(rows, windows, {"X": {"median": 20.0}}, [2024], min_cars=1)["n"] == 1
    assert fit_sc_pit_loss(rows, windows, {"X": {"median": 20.0}}, [2024]) is None       # only one car ran plain laps
