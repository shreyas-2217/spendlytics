"""Plotly chart builders — one palette, money-aware formatting, no chart junk."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

INDIGO = "#4F46E5"
TEAL = "#0D9488"
PALETTE = [
    INDIGO,
    TEAL,
    "#F59E0B",
    "#EC4899",
    "#8B5CF6",
    "#0EA5E9",
    "#84CC16",
    "#EF4444",
    "#64748B",
    "#14B8A6",
    "#F97316",
    "#6366F1",
    "#22C55E",
    "#E11D48",
    "#A855F7",
    "#0F766E",
]


def inr(value: float) -> str:
    return f"₹{value:,.0f}"


def inr_compact(value: float) -> str:
    """₹1.27L / ₹21.1k — short numbers for tight spaces."""
    if value >= 1e7:
        return f"₹{value / 1e7:.2f}Cr"
    if value >= 1e5:
        return f"₹{value / 1e5:.2f}L"
    if value >= 1e3:
        return f"₹{value / 1e3:.1f}k"
    return f"₹{value:,.0f}"


def _style(fig: go.Figure, height: int = 380) -> go.Figure:
    fig.update_layout(
        template="plotly_white",
        height=height,
        margin=dict(l=10, r=10, t=40, b=10),
        legend=dict(orientation="h", yanchor="bottom", y=-0.25, x=0),
        font=dict(family="Inter, Segoe UI, sans-serif", size=13),
    )
    return fig


def _title(text: str) -> dict:
    return dict(text=text, x=0, xanchor="left", font=dict(size=15))


def monthly_spend_figure(monthly: pd.Series) -> go.Figure | None:
    """Bars per month with an average line — the 'am I normal?' view."""
    if monthly.empty:
        return None
    frame = monthly.reset_index()
    frame.columns = ["month", "amount"]
    frame["month"] = frame["month"].astype(str)
    average = float(frame["amount"].mean())

    fig = px.bar(frame, x="month", y="amount")
    fig.update_traces(
        marker_color=INDIGO,
        hovertemplate="%{x}<br>₹%{y:,.0f}<extra></extra>",
    )
    fig.add_hline(
        y=average,
        line_dash="dot",
        line_color="#94A3B8",
        annotation_text=f"avg {inr(average)}",
        annotation_position="top left",
    )
    fig.update_xaxes(title=None)
    fig.update_yaxes(title=None, tickprefix="₹", separatethousands=True)
    fig.update_layout(title=_title("Monthly spending"))
    return _style(fig)


def category_figure(breakdown: pd.DataFrame) -> go.Figure | None:
    """Donut of where the money went — top 6 categories + Other."""
    if breakdown.empty:
        return None
    frame = breakdown[["category", "total"]].sort_values("total", ascending=False)
    frame = frame.reset_index(drop=True)
    has_other = len(frame) > 7
    if has_other:
        tail = frame.iloc[6:]
        frame = pd.concat(
            [
                frame.iloc[:6],
                pd.DataFrame([{"category": "Other", "total": float(tail["total"].sum())}]),
            ],
            ignore_index=True,
        )
    total = float(frame["total"].sum()) or 1.0
    shares = frame["total"] / total
    fig = px.pie(
        frame,
        names="category",
        values="total",
        hole=0.55,
        color_discrete_sequence=PALETTE,
    )
    # px.pie sorts slices by value — pin "Other" to a neutral gray in the final order.
    labels = list(fig.data[0].labels)
    fig.update_traces(
        marker=dict(
            colors=[
                "#94A3B8" if label == "Other" else PALETTE[index % len(PALETTE)]
                for index, label in enumerate(labels)
            ]
        ),
    )
    fig.update_traces(
        text=[f"{share * 100:.0f}%" if share >= 0.05 else "" for share in shares],
        textinfo="text",
        textfont_size=12,
        hovertemplate="%{label}<br>₹%{value:,.0f} (%{percent})<extra></extra>",
    )
    fig.update_layout(
        title=_title("Where it went"),
        annotations=[
            dict(
                text=f"<b>{inr_compact(total)}</b><br><span style='font-size:11px'>total</span>",
                x=0.5,
                y=0.5,
                showarrow=False,
                font=dict(size=17),
            )
        ],
    )
    fig = _style(fig, height=430)
    fig.update_layout(
        margin=dict(l=10, r=10, t=40, b=95),
        legend=dict(
            orientation="h",
            yanchor="top",
            y=-0.02,
            x=0.5,
            xanchor="center",
            font=dict(size=11),
        ),
    )
    return fig


def merchants_figure(merchants: pd.DataFrame) -> go.Figure | None:
    """Horizontal bars of the top merchants."""
    if merchants.empty:
        return None
    frame = merchants.sort_values("total")
    fig = px.bar(frame, x="total", y="merchant", orientation="h", color_discrete_sequence=[INDIGO])
    fig.update_traces(hovertemplate="%{y}<br>₹%{x:,.0f}<extra></extra>")
    fig.update_xaxes(title=None, tickprefix="₹", separatethousands=True)
    fig.update_yaxes(title=None)
    fig.update_layout(title=_title("Top merchants"))
    return _style(fig, height=max(340, 28 * len(frame) + 90))


def result_figure(result: pd.DataFrame) -> go.Figure | None:
    """Best-effort chart for a copilot SQL result (label + one numeric column)."""
    if result is None or result.empty or len(result.columns) < 2:
        return None
    numeric = [column for column in result.columns if pd.api.types.is_numeric_dtype(result[column])]
    if len(numeric) != 1:
        return None
    value_column = numeric[0]
    others = [column for column in result.columns if column != value_column]
    if not others:
        return None
    label_column = others[0]
    if len(result) == 1:
        return None  # single values are shown as a metric instead

    if pd.api.types.is_datetime64_any_dtype(result[label_column]):
        fig = px.line(
            result, x=label_column, y=value_column, markers=True, color_discrete_sequence=[INDIGO]
        )
    else:
        frame = result.head(12).copy()
        fig = px.bar(frame, x=label_column, y=value_column, color_discrete_sequence=[TEAL])
        fig.update_xaxes(tickangle=-30)
    fig.update_layout(title=None)
    return _style(fig, height=340)
