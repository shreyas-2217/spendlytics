"""Smoke tests: the whole app boots and the sample-data flow renders."""

from pathlib import Path

from streamlit.testing.v1 import AppTest

APP_PATH = Path(__file__).resolve().parent.parent / "app.py"


def test_app_boots_without_exceptions():
    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.run()
    assert not at.exception


def test_sample_data_flow():
    at = AppTest.from_file(APP_PATH, default_timeout=60)
    at.run()
    assert not at.exception

    sample_button = next(button for button in at.button if "sample data" in button.label)
    sample_button.click()
    at.run()

    assert not at.exception
    markdown_values = [element.value for element in at.markdown]
    assert any("stat-strip" in value and "Total spent" in value for value in markdown_values)
