"""Chart builders: structure, grouping, and graceful degrade."""

import pandas as pd

from src import charts


def test_inr_compact_formats():
    assert charts.inr_compact(126560) == "₹1.27L"
    assert charts.inr_compact(21093) == "₹21.1k"
    assert charts.inr_compact(950) == "₹950"


def test_category_figure_groups_tail_into_other():
    breakdown = pd.DataFrame(
        {
            "category": [f"Cat {index}" for index in range(10)],
            "total": [100.0, 90.0, 80.0, 70.0, 60.0, 50.0, 40.0, 30.0, 20.0, 10.0],
        }
    )
    figure = charts.category_figure(breakdown)
    assert figure is not None
    labels = list(figure.data[0].labels)
    assert len(labels) == 7
    assert labels[-1] == "Other"
    # Other aggregates the tail: 40 + 30 + 20 + 10
    assert float(figure.data[0].values[-1]) == 100.0


def test_category_figure_keeps_small_breakdown_intact():
    breakdown = pd.DataFrame({"category": ["Rent", "Food"], "total": [500.0, 300.0]})
    figure = charts.category_figure(breakdown)
    assert figure is not None
    assert list(figure.data[0].labels) == ["Rent", "Food"]


def test_category_figure_empty_returns_none():
    empty = pd.DataFrame(columns=["category", "total"])
    assert charts.category_figure(empty) is None


def test_monthly_spend_figure_empty_returns_none():
    assert charts.monthly_spend_figure(pd.Series(dtype=float)) is None


def test_result_figure_requires_label_and_number():
    assert charts.result_figure(pd.DataFrame({"total": [10.0]})) is None
    categories = pd.DataFrame({"category": ["Rent", "Food"], "total": [500.0, 300.0]})
    assert charts.result_figure(categories) is not None
