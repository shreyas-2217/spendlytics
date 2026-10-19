"""Canonical transaction schema shared across parsers, analytics, and the UI."""

from __future__ import annotations

import pandas as pd

#: Every parsed statement is normalised to exactly these columns.
CANONICAL_COLUMNS = [
    "date",
    "description",
    "merchant",
    "amount",
    "direction",
    "category",
    "source",
]


def empty_transactions() -> pd.DataFrame:
    """An empty DataFrame with the canonical schema."""
    return pd.DataFrame(columns=CANONICAL_COLUMNS)


def finalize_transactions(df: pd.DataFrame, source: str) -> pd.DataFrame:
    """Coerce a freshly parsed frame into the canonical schema.

    - ``date`` becomes datetime64; rows without a valid date are dropped
    - ``amount`` becomes a positive float; zero/NaN rows are dropped
    - ``direction`` is lower-cased ("debit" or "credit")
    - missing optional columns are created, and rows are sorted by date
    """
    if df is None or len(df) == 0:
        return empty_transactions()

    frame = df.copy()
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    frame["amount"] = pd.to_numeric(frame["amount"], errors="coerce").abs()
    frame["direction"] = frame["direction"].astype(str).str.lower().str.strip()
    frame = frame.dropna(subset=["date", "amount"])
    frame = frame[frame["amount"] > 0]
    frame = frame[frame["direction"].isin(["debit", "credit"])]

    if "description" not in frame.columns:
        frame["description"] = ""
    frame["description"] = frame["description"].fillna("").astype(str)

    for column in ("merchant", "category"):
        if column not in frame.columns:
            frame[column] = ""
        frame[column] = frame[column].fillna("").astype(str)

    frame["source"] = source
    return frame[CANONICAL_COLUMNS].sort_values("date").reset_index(drop=True)
