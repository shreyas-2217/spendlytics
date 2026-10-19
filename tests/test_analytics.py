"""Tests for the analytics engine: summaries, subscriptions, anomalies, KPIs."""

import pandas as pd
import pytest

from src import analytics

COLUMNS = ["date", "description", "merchant", "amount", "direction", "category", "source"]


def make_df(rows: list[list]) -> pd.DataFrame:
    frame = pd.DataFrame(rows, columns=["date", "merchant", "category", "amount", "direction"])
    frame["description"] = frame["merchant"]
    frame["source"] = "test"
    frame["date"] = pd.to_datetime(frame["date"])
    return frame[COLUMNS]


def test_detect_subscriptions():
    rows = []
    for month in range(5, 11):
        rows.append([f"2026-{month:02d}-05", "Netflix", "Subscriptions", 649.0, "debit"])
    for when, amount in [
        ("2026-05-03", 250),
        ("2026-05-17", 410),
        ("2026-06-02", 300),
        ("2026-06-21", 180),
        ("2026-07-04", 520),
        ("2026-07-19", 260),
    ]:
        rows.append([when, "Swiggy", "Food Delivery", float(amount), "debit"])
    frame = make_df(rows)

    subscriptions = analytics.detect_subscriptions(frame)
    assert list(subscriptions["merchant"]) == ["Netflix"]
    assert int(subscriptions.iloc[0]["charges"]) == 6
    assert float(subscriptions.iloc[0]["estimated_monthly"]) == pytest.approx(649.0)


def test_find_anomalies_flags_the_spike_month():
    rows = []
    for month in range(5, 11):
        rows.append([f"2026-{month:02d}-10", "Swiggy", "Food Delivery", 1000.0, "debit"])
    rows.append(["2026-09-15", "Croma", "Shopping", 9000.0, "debit"])
    frame = make_df(rows)

    anomalies = analytics.find_anomalies(frame)
    assert len(anomalies) == 1
    assert anomalies[0]["month"] == "2026-09"
    assert anomalies[0]["driver"] == "Shopping"


def test_overview_kpis_respects_transfer_filter():
    rows = [
        ["2026-09-05", "Swiggy", "Food Delivery", 500.0, "debit"],
        ["2026-09-10", "Netflix", "Subscriptions", 649.0, "debit"],
        ["2026-09-01", "Dad", "Transfers", 9000.0, "credit"],
        ["2026-09-12", "Aarav", "Transfers", 200.0, "debit"],
        ["2026-10-02", "Swiggy", "Food Delivery", 700.0, "debit"],
    ]
    frame = make_df(rows)

    without_transfers = analytics.overview_kpis(frame, include_transfers=False)
    assert without_transfers["total_spend"] == 1849.0
    assert without_transfers["months"] == 2
    assert without_transfers["top_category"] == "Food Delivery"

    with_transfers = analytics.overview_kpis(frame, include_transfers=True)
    assert with_transfers["total_spend"] == 2049.0


def test_monthly_summary():
    rows = [
        ["2026-09-05", "Swiggy", "Food Delivery", 500.0, "debit"],
        ["2026-09-01", "Dad", "Transfers", 9000.0, "credit"],
        ["2026-10-02", "Swiggy", "Food Delivery", 700.0, "debit"],
    ]
    frame = make_df(rows)
    summary = analytics.monthly_summary(frame)
    assert list(summary["month"]) == ["2026-09", "2026-10"]
    assert float(summary.iloc[0]["spend"]) == 500.0
    assert float(summary.iloc[0]["credits"]) == 9000.0
    assert int(summary.iloc[1]["transactions"]) == 1
