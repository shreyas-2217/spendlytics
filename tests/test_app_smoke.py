"""Smoke tests: the whole app boots and the sample-data flow renders."""

import os
from pathlib import Path

from streamlit.testing.v1 import AppTest

# Tests must never spend API quota — force the offline path.
os.environ["SPENDLYTICS_DISABLE_LLM"] = "1"

APP_PATH = Path(__file__).resolve().parent.parent / "app.py"


def test_app_boots_without_exceptions():
    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.run()
    assert not at.exception


def test_sample_data_flow():
    at = AppTest.from_file(APP_PATH, default_timeout=60)
    at.run()
    assert not at.exception

    sample_button = next(button for button in at.button if "demo statement" in button.label)
    sample_button.click()
    at.run()

    assert not at.exception
    markdown_values = [element.value for element in at.markdown]
    assert any("stat-strip" in value and "Total spent" in value for value in markdown_values)
