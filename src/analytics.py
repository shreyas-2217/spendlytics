"""Spending analytics built on pandas — pure functions, easy to test."""

from __future__ import annotations

import pandas as pd

TRANSFER_CATEGORY = "Transfers"


def inr(value: float) -> str:
    """Format a number as Indian rupees, e.g. ``₹12,340``."""
    return f"₹{value:,.0f}"


def spend_rows(df: pd.DataFrame, include_transfers: bool = True) -> pd.DataFrame:
    """Debit rows, optionally excluding person-to-person transfers."""
    rows = df[df["direction"] == "debit"]
    if not include_transfers:
        rows = rows[rows["category"] != TRANSFER_CATEGORY]
    return rows


def monthly_spend(rows: pd.DataFrame) -> pd.Series:
    """Total spend per calendar month, sorted."""
    if rows.empty:
        return pd.Series(dtype=float)
    grouped = rows.groupby(rows["date"].dt.to_period("M"))["amount"].sum()
    grouped.index.name = "month"
    return grouped.sort_index()


def monthly_summary(df: pd.DataFrame) -> pd.DataFrame:
    """One row per month: spend, credits received, transaction count."""
    if df.empty:
        return pd.DataFrame(columns=["month", "spend", "credits", "transactions"])
    frame = df.copy()
    frame["month"] = frame["date"].dt.to_period("M").astype(str)
    spends = frame[frame["direction"] == "debit"].groupby("month")["amount"].sum()
    credits = frame[frame["direction"] == "credit"].groupby("month")["amount"].sum()
    counts = frame.groupby("month")["amount"].size()
    out = pd.DataFrame({"spend": spends, "credits": credits, "transactions": counts}).fillna(0.0)
    return out.reset_index().sort_values("month").reset_index(drop=True)


def category_breakdown(rows: pd.DataFrame) -> pd.DataFrame:
    """Spend per category with share and month-over-month change."""
    if rows.empty:
        return pd.DataFrame(columns=["category", "total", "share", "transactions", "change_pct"])
    totals = rows.groupby("category").agg(
        total=("amount", "sum"), transactions=("amount", "size")
    )
    totals["share"] = totals["total"] / totals["total"].sum()

    months = sorted(rows["date"].dt.to_period("M").unique())
    if len(months) >= 2:
        period = rows["date"].dt.to_period("M")
        last, previous = months[-1], months[-2]
        changes = {}
        for category in totals.index:
            current = rows[(rows["category"] == category) & (period == last)]["amount"].sum()
            before = rows[(rows["category"] == category) & (period == previous)]["amount"].sum()
            changes[category] = ((current - before) / before * 100) if before > 0 else None
        totals["change_pct"] = pd.Series(changes)
    else:
        totals["change_pct"] = None
    return totals.sort_values("total", ascending=False).reset_index()


def top_merchants(rows: pd.DataFrame, count: int = 12) -> pd.DataFrame:
    """The merchants that took the most money."""
    if rows.empty:
        return pd.DataFrame(columns=["merchant", "category", "total", "transactions", "average"])
    grouped = rows.groupby(["merchant", "category"], as_index=False).agg(
        total=("amount", "sum"),
        transactions=("amount", "size"),
        average=("amount", "mean"),
    )
    return grouped.sort_values("total", ascending=False).head(count).reset_index(drop=True)


def detect_subscriptions(df: pd.DataFrame) -> pd.DataFrame:
    """Find likely recurring charges: stable amount, ~monthly cadence, >=3 charges."""
    rows = df[df["direction"] == "debit"]
    found: list[dict] = []
    for merchant, group in rows.groupby("merchant"):
        if len(group) < 3:
            continue
        ordered = group.sort_values("date")
        gaps = ordered["date"].diff().dt.days.dropna()
        median_gap = gaps.median()
        if pd.isna(median_gap) or not (24 <= median_gap <= 36):
            continue
        amounts = ordered["amount"]
        mean = float(amounts.mean())
        if mean <= 0:
            continue
        variability = float((amounts - mean).abs().mean()) / mean
        if variability > 0.2:
            continue
        months = int(ordered["date"].dt.to_period("M").nunique())
        modes = ordered["category"].mode()
        found.append(
            {
                "merchant": merchant,
                "category": modes.iat[0] if not modes.empty else "Other",
                "average": mean,
                "charges": len(ordered),
                "months": months,
                "estimated_monthly": float(amounts.sum()) / months if months else 0.0,
            }
        )
    frame = pd.DataFrame(
        found,
        columns=["merchant", "category", "average", "charges", "months", "estimated_monthly"],
    )
    if frame.empty:
        return frame
    return frame.sort_values("estimated_monthly", ascending=False).reset_index(drop=True)


def find_anomalies(rows: pd.DataFrame, threshold: float = 1.3) -> list[dict]:
    """Months whose spend is far above the user's own average."""
    series = monthly_spend(rows)
    if len(series) < 4:
        return []
    mean, std = float(series.mean()), float(series.std(ddof=0))
    if not std:
        return []
    anomalies: list[dict] = []
    for period, value in series.items():
        z_score = (float(value) - mean) / std
        if z_score < threshold:
            continue
        month_rows = rows[rows["date"].dt.to_period("M") == period]
        by_category = month_rows.groupby("category")["amount"].sum()
        average_by_category = rows.groupby("category")["amount"].sum() / len(series)
        drivers = (by_category - average_by_category).sort_values(ascending=False)
        driver = str(drivers.index[0]) if len(drivers) else None
        anomalies.append(
            {
                "month": str(period),
                "spend": float(value),
                "multiple": float(value) / mean,
                "driver": driver,
                "driver_amount": float(by_category.get(driver, 0.0)) if driver else 0.0,
            }
        )
    return anomalies


def overview_kpis(df: pd.DataFrame, include_transfers: bool = True) -> dict:
    """Headline numbers for the overview tab."""
    rows = spend_rows(df, include_transfers)
    months = int(rows["date"].dt.to_period("M").nunique()) if not rows.empty else 0
    total = float(rows["amount"].sum()) if not rows.empty else 0.0
    by_category = (
        rows.groupby("category")["amount"].sum() if not rows.empty else pd.Series(dtype=float)
    )
    subscriptions = detect_subscriptions(df)
    food = float(by_category.get("Food Delivery", 0.0)) + float(by_category.get("Eating Out", 0.0))
    return {
        "total_spend": total,
        "months": months,
        "average_monthly": (total / months) if months else 0.0,
        "top_category": str(by_category.idxmax()) if not by_category.empty else "—",
        "top_category_amount": float(by_category.max()) if not by_category.empty else 0.0,
        "transactions": int(len(rows)),
        "recurring_count": int(len(subscriptions)),
        "recurring_monthly": (
            float(subscriptions["estimated_monthly"].sum()) if not subscriptions.empty else 0.0
        ),
        "food_dining_share": (food / total) if total else 0.0,
    }


def headline_insight(rows: pd.DataFrame) -> str | None:
    """One-sentence anomaly summary, if any month stands out."""
    anomalies = find_anomalies(rows)
    if not anomalies:
        return None
    latest = anomalies[-1]
    month_label = pd.Period(str(latest["month"]), freq="M").strftime("%B %Y")
    return (
        f"{month_label} was {latest['multiple']:.1f}× your average month — "
        f"driven by {latest['driver']} ({inr(latest['driver_amount'])})."
    )
