"""Tests for the synthetic sample data generator."""

import pandas as pd

from src.models import CANONICAL_COLUMNS
from src.sample_data import generate_sample_df


def test_sample_is_deterministic():
    first = generate_sample_df(seed=7)
    second = generate_sample_df(seed=7)
    assert len(first) == len(second)
    assert first["amount"].sum() == second["amount"].sum()


def test_sample_schema_and_content():
    frame = generate_sample_df()
    assert list(frame.columns) == CANONICAL_COLUMNS
    assert len(frame) > 120
    assert set(frame["direction"]) == {"debit", "credit"}
    assert frame["date"].max() <= pd.Timestamp("2026-10-18 23:59:59")
    assert (frame["amount"] > 0).all()
