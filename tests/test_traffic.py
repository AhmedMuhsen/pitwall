import numpy as np
import pandas as pd
import pytest

from pitwall.traffic import (fit_traffic_penalty, gap_ahead, real_gaps, start_times, traffic_penalty,
                             traffic_timeline)


class ZeroModel:
    def predict(self, X):
        return np.zeros(len(X))


def lap_row(driver, lap, start, delta=0.0, session=1, clean=True):
    return {"session_key": session, "driver_number": driver, "lap_number": lap, "date_start": start,
            "delta": delta, "is_clean": clean, "compound": "HARD", "circuit": "X", "tyre_age": lap,
            "race_fraction": lap / 10}


def test_start_times_and_gap_ahead():
    rows = [lap_row(1, 2, "2024-01-01T12:00:10+00:00"), lap_row(2, 2, "2024-01-01T12:00:12.500000+00:00"),
            lap_row(3, 2, "2024-01-01T12:00:11+00:00"), lap_row(3, 3, None)]
    field = start_times(rows)

    assert 3 not in field[3]                              # a lap with no date_start is left out
    base = field[1][2]
    assert gap_ahead(field[2][2], 2, field, exclude=2) == pytest.approx(1.5)    # car 3 started at :11
    assert gap_ahead(field[1][2], 2, field, exclude=1) is None                  # car 1 leads lap 2
    assert gap_ahead(base + 100, 2, field) == pytest.approx(100 - 2.5)          # nearest is car 2, at :12.5


def test_real_gaps_ignores_other_lap_numbers():
    rows = [lap_row(1, 2, "2024-01-01T12:00:10+00:00"), lap_row(2, 3, "2024-01-01T12:00:09+00:00")]

    gaps = real_gaps(rows)

    assert gaps == {(1, 2): None, (2, 3): None}   # nobody else started the same lap number


def test_fit_traffic_penalty_hand_example():
    # Lap 1 is never used. Car A leads (no gap). Car B starts lap 2 0.4 s behind A (bin 0, < 0.5 s)
    # and lap 3 3.0 s behind (bin 4, 2.5-4 s). B's deltas 1.0 and 0.0 average 0.5, so its residuals
    # are +0.5 and -0.5. A's deltas are 0.0 everywhere, so its residuals are 0 (no-car-ahead bin).
    rows = [lap_row(1, 1, "2024-01-01T12:00:00+00:00", 9.0), lap_row(2, 1, "2024-01-01T12:00:00.100000+00:00", 9.0),
            lap_row(1, 2, "2024-01-01T12:01:10+00:00"), lap_row(2, 2, "2024-01-01T12:01:10.400000+00:00", 1.0),
            lap_row(1, 3, "2024-01-01T12:02:40+00:00"), lap_row(2, 3, "2024-01-01T12:02:43+00:00", 0.0)]

    table = fit_traffic_penalty(rows, ZeroModel())

    assert table["edges"] == [0.5, 1.0, 1.5, 2.5, 4.0]
    assert table["n"] == [1, 0, 0, 0, 1, 2]
    assert table["mean"] == pytest.approx([0.5, 0.0, 0.0, 0.0, -0.5, 0.0])


def test_traffic_penalty_lookup():
    table = {"edges": [0.5, 1.0], "mean": [0.5, 0.2, -0.1], "n": [1, 1, 1]}

    assert traffic_penalty(0.2, table) == 0.5
    assert traffic_penalty(0.5, table) == 0.2        # a gap of exactly 0.5 s is in the next bin
    assert traffic_penalty(1.0, table) == -0.1
    assert traffic_penalty(None, table) == -0.1      # no car ahead


TABLE = {"edges": [0.5, 1.0], "mean": [0.5, 0.2, -0.1], "n": [1, 1, 1]}
FREE_100 = pd.DataFrame({"lap_number": [1, 2, 3, 4], "lap_time": [100.0] * 4})
# Our car really started lap n at 100 * (n - 1). Another car started lap n 0.2 s, 1.0 s, 0.3 s
# ahead of us on laps 2, 3, 4.
REAL = {n: 100.0 * (n - 1) for n in (1, 2, 3, 4)}
FIELD = {7: {1: -1.0, 2: 99.8, 3: 199.0, 4: 299.7}}


def test_traffic_timeline_real_strategy_sits_where_it_really_was():
    result = traffic_timeline(FREE_100, [], 20.0, REAL, FIELD, TABLE)

    laps = result["laps"]
    assert np.isnan(laps["traffic_gap"].iloc[0])               # lap 1: no traffic penalty, no gap
    assert laps["traffic_gap"].tolist()[1:] == pytest.approx([0.2, 1.0, 0.3])
    # Lap 1: no penalty. Lap 2: gap 0.2 -> +0.5. Lap 3: gap 1.0 -> -0.1. Lap 4: gap 0.3 -> +0.5.
    assert laps["lap_time"].tolist() == pytest.approx([100.0, 100.5, 99.9, 100.5])
    assert result["cum"] == pytest.approx({1: 0.0, 2: 100.0, 3: 200.5, 4: 300.4})


def test_traffic_timeline_anchored_strategy_moves_through_the_field():
    anchor = traffic_timeline(FREE_100, [], 20.0, REAL, FIELD, TABLE)["cum"]
    faster = FREE_100.assign(lap_time=99.0)      # 1 s a lap quicker in free air

    result = traffic_timeline(faster, [], 20.0, REAL, FIELD, TABLE, anchor=anchor)

    # It starts lap 2 at 100 + 99 - 100 = 99.0, before the other car (99.8): nobody ahead, free air -0.1.
    # Lap 3: 200 + 197.9 - 200.5 = 197.4 < 199.0, free air again. Lap 4: 296.4 < 299.7, free air.
    assert result["laps"]["traffic_gap"].isna().all()
    assert result["laps"]["lap_time"].tolist() == pytest.approx([99.0, 98.9, 98.9, 98.9])


def test_traffic_timeline_no_penalty_on_in_lap_out_lap_and_pit_loss_counts():
    result = traffic_timeline(FREE_100, [2], 20.0, REAL, FIELD, TABLE)

    # Pit on lap 2: lap 2 (in-lap) and lap 3 (out-lap) get no penalty; lap 4 starts at the real 300 and
    # sees the car 0.3 s ahead (+0.5). The stop adds 20 s to the elapsed time after lap 2.
    assert result["laps"]["traffic_penalty"].tolist() == pytest.approx([0.0, 0.0, 0.0, 0.5])
    assert result["cum"] == pytest.approx({1: 0.0, 2: 100.0, 3: 220.0, 4: 320.0})


def test_traffic_timeline_lap_without_real_start_continues_from_previous_lap():
    real = {1: 0.0, 2: 100.0, 4: 300.0}     # lap 3 start is missing

    result = traffic_timeline(FREE_100, [], 20.0, real, FIELD, TABLE)

    # Lap 3 is assumed to start at 100 + 100.5 = 200.5, after the other car (199.0): gap 1.5 -> bin 2 (-0.1).
    assert result["laps"]["traffic_gap"].tolist()[2] == pytest.approx(1.5)


def test_traffic_timeline_without_any_start_time_runs_in_free_air():
    result = traffic_timeline(FREE_100, [], 20.0, {}, FIELD, TABLE)

    assert result["laps"]["traffic_gap"].isna().all()
    assert result["laps"]["lap_time"].tolist() == pytest.approx([100.0, 99.9, 99.9, 99.9])
