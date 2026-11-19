import pytest

from pitwall.conformal import (
    conformal_half_width,
    coverage,
    load_calibration,
    rolling_coverage,
    summarise_target,
)


def test_half_width_is_the_corrected_quantile_of_the_absolute_errors():
    errors = [3.0, -1.0, 4.0, -2.0, 5.0]          # absolute, sorted: 1 2 3 4 5

    assert conformal_half_width(errors, 0.8) == 5.0   # k = ceil(6 * 0.8) = 5
    assert conformal_half_width(errors, 0.5) == 3.0   # k = ceil(6 * 0.5) = 3
    assert conformal_half_width(errors, 0.2) == 2.0   # k = ceil(6 * 0.2) = 2


def test_half_width_refuses_too_few_errors_and_bad_levels():
    assert conformal_half_width([1.0, 2.0, 3.0, 4.0], 0.8) == 4.0       # 4 errors is exactly enough
    with pytest.raises(ValueError, match="too few"):
        conformal_half_width([1.0, 2.0, 3.0], 0.8)                      # k = ceil(3.2) = 4 > 3
    with pytest.raises(ValueError, match="too few"):
        conformal_half_width([], 0.8)
    for level in (0.0, 1.0, 1.5, -0.1):
        with pytest.raises(ValueError, match="between 0 and 1"):
            conformal_half_width([1.0] * 20, level)


def test_coverage():
    assert coverage([1.0, -2.0, 3.0, -4.0], 2.0) == 0.5
    assert coverage([0.5, -0.5], 0.5) == 1.0                            # the boundary counts as covered
    with pytest.raises(ValueError):
        coverage([], 1.0)


def test_rolling_coverage_hand_example():
    # Batch 1: calibrated on [1, 2, 3, 4]: n = 4, k = 4, half-width 4. Errors 2 (in) and 6 (out).
    # Batch 2: calibrated on [1, 2, 3, 4, 2, 6]: n = 6, k = ceil(5.6) = 6, half-width 6. Error 3 is in.
    result = rolling_coverage([1.0, 2.0, 3.0, 4.0], [[2.0, -6.0], [], [3.0]], 0.8)

    assert [b["half_width"] for b in result["batches"]] == [4.0, 6.0]     # the empty batch is skipped
    assert [(b["n"], b["covered"]) for b in result["batches"]] == [(2, 1), (1, 1)]
    assert result["coverage"] == pytest.approx(2 / 3)
    assert result["mean_half_width"] == pytest.approx((4 * 2 + 6 * 1) / 3)


def test_rolling_coverage_needs_a_batch_and_enough_calibration():
    with pytest.raises(ValueError, match="No batch"):
        rolling_coverage([1.0] * 10, [[], []])
    with pytest.raises(ValueError, match="too few"):
        rolling_coverage([1.0, 2.0], [[1.0]])


def test_summarise_target_hand_example():
    result = summarise_target([1.0, 2.0, 3.0, 4.0], [[2.0, -6.0], [3.0]], 0.8)

    # static: half-width 4 on the calibration errors; the test errors 2, 6, 3 -> 2 of 3 covered.
    assert result["static"] == {"half_width": 4.0, "coverage": pytest.approx(2 / 3)}
    assert result["rolling"]["coverage"] == pytest.approx(2 / 3)
    # all seven errors: |1 2 3 4 2 6 3| sorted 1 2 2 3 3 4 6, k = ceil(8 * 0.8) = 7 -> 6
    assert result["half_width"] == 6.0
    assert (result["n_calibration"], result["n_test"], result["level"]) == (7, 3, 0.8)


def test_load_calibration(tmp_path):
    path = tmp_path / "calibration.json"
    path.write_text('{"level": 0.8, "targets": {"lap": {"half_width": 0.9}}}')

    assert load_calibration(path)["targets"]["lap"]["half_width"] == 0.9
    assert load_calibration(tmp_path / "missing.json") is None


def test_coverage_note_states_the_coverage_with_the_half_width_it_was_measured_at():
    from pitwall.conformal import coverage_note
    calibration = {"test_year": 2025, "calibration_years": [2023, 2024],
                   "targets": {"race_total": {"half_width": 17.2, "static": {"half_width": 16.04, "coverage": 0.7108}}}}

    assert coverage_note(calibration, "race_total", "race totals") == \
        "calibrated on 2023/24 alone (±16.0 s) it covered 71% of 2025 race totals"
    one_year = {**calibration, "calibration_years": [2024]}
    assert coverage_note(one_year, "race_total", "values").startswith("calibrated on 2024 alone")
    with pytest.raises(KeyError):
        coverage_note(calibration, "gap", "gaps")
