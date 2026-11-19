"""The real Streamlit app, run headlessly on the committed data with Streamlit's own AppTest (no browser, no new dependency).

These check that the page renders without an exception and that the main controls work; they do not check every chart."""
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).parent.parent / "app.py")


def run_app() -> AppTest:
    return AppTest.from_file(APP, default_timeout=240).run()


def problems(at: AppTest) -> tuple[list, list]:
    return [e.value for e in at.exception], [e.value for e in at.error]


@pytest.fixture(scope="module")
def first_page() -> AppTest:
    return run_app()


def test_the_first_page_renders_without_an_exception_or_error(first_page):
    assert problems(first_page) == ([], [])
    assert [t.value for t in first_page.title] == ["PitWall"]
    assert len(first_page.selectbox[0].options) == 50                       # the races offered
    assert [m.label for m in first_page.metric] == ["Real race time", "Model, same strategy"]


def test_the_intervals_say_which_calibration_their_coverage_was_measured_with(first_page):
    text = " ".join(c.value for c in first_page.caption)

    assert "calibrated on 2023/24 alone" in text and "covered" in text


def test_switching_race_car_and_traffic_keeps_the_page_working():
    at = run_app()
    before = [m.value for m in at.metric]

    race = at.selectbox[0]
    race.select(race.options[3]).run()
    assert problems(at) == ([], [])
    assert [m.value for m in at.metric] != before                            # a different race has different times

    at.selectbox[1].select_index(2).run()
    assert problems(at) == ([], [])

    with_traffic = at.metric[1].value
    at.toggle[0].set_value(False).run()
    assert problems(at) == ([], [])
    assert at.metric[1].value != with_traffic                                # traffic changes the simulated time


def test_a_custom_strategy_is_checked_in_plain_words_and_added_when_valid():
    at = run_app()
    at.selectbox[2].select("MEDIUM")
    at.selectbox[3].select("MEDIUM")
    at.checkbox[0].set_value(True).run()

    exceptions, errors = problems(at)
    assert exceptions == []
    assert len(errors) == 1 and "can't be used" in errors[0] and "two different dry compounds" in errors[0]

    at.selectbox[3].select("HARD").run()

    assert problems(at) == ([], [])
    assert any(option.startswith("Yours:") for option in at.multiselect[0].options)
