"""Spendlytics — Streamlit app.

Run locally with:  streamlit run app.py
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from src import analytics, charts, copilot, sample_data
from src.categorizer import categorize
from src.llm import LLMClient
from src.parsers import ParseError, parse_statement

APP_NAME = "Spendlytics"
APP_VERSION = "0.1.0"
AUTHOR = "Shreyas V Melligeri"

st.set_page_config(
    page_title=f"{APP_NAME} · UPI spending, explained",
    page_icon="💸",
    layout="wide",
    initial_sidebar_state="expanded",
)

CSS = """
<style>
.block-container {padding-top: 2.2rem; padding-bottom: 3rem; max-width: 1150px;}
div[data-testid="stMetric"] {
    background: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 12px;
    padding: 14px 16px;
}
div[data-testid="stMetric"] label {color: #475569;}
div[data-testid="stMetricValue"] {font-size: 1.4rem;}
.sp-hero {font-size: 2.4rem; font-weight: 800; letter-spacing: -0.02em; margin-bottom: 0.2rem;}
.sp-sub {font-size: 1.05rem; color: #475569; margin-bottom: 1.2rem;}
.sp-badge {display:inline-block; background:#EEF2FF; color:#4338CA; border-radius:999px;
    padding:2px 10px; font-size:0.78rem; font-weight:600; margin-right:6px;}
.sp-card {background:#F8FAFC; border:1px solid #E2E8F0; border-radius:12px; padding:14px 16px;
    height:100%;}
.sp-card h4 {margin: 0 0 6px 0; font-size: 0.95rem;}
.sp-card p {margin: 0; color:#475569; font-size: 0.88rem;}
.stat-strip {display:grid; grid-template-columns:repeat(auto-fit, minmax(205px, 1fr)); gap:10px;
    margin-bottom:0.6rem;}
.stat {background:#F8FAFC; border:1px solid #E2E8F0; border-radius:12px; padding:14px 16px;}
.stat-label {font-size:0.72rem; text-transform:uppercase; letter-spacing:0.05em; color:#64748B;}
.stat-value {font-size:1.5rem; font-weight:700; color:#0F172A; line-height:1.3; white-space:nowrap;
    overflow:hidden; text-overflow:ellipsis;}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)


# ---------------------------------------------------------------- helpers

def money(value: float) -> str:
    return f"₹{value:,.0f}"


def money_frame(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """Render money columns as pre-formatted strings (version-proof display)."""
    out = frame.copy()
    for column in columns:
        if column in out.columns:
            out[column] = out[column].map(
                lambda value: f"₹{value:,.0f}" if pd.notna(value) else ""
            )
    return out


@st.cache_resource
def get_client() -> LLMClient:
    return LLMClient()


def apply_data(frame: pd.DataFrame, meta: dict) -> None:
    """Categorize freshly parsed data and store it in the session."""
    client = get_client()
    with st.spinner("Categorizing merchants…"):
        frame, stats = categorize(frame, client)
    st.session_state["df"] = frame
    st.session_state["stats"] = stats
    st.session_state["meta"] = meta
    st.session_state["chat"] = []


def reset_data() -> None:
    for key in ("df", "stats", "meta", "chat", "upload_name"):
        st.session_state.pop(key, None)


def load_sample() -> None:
    frame = sample_data.generate_sample_df()
    apply_data(frame, {"source": "sample", "rows_read": len(frame)})


# ---------------------------------------------------------- session state

st.session_state.setdefault("df", None)
st.session_state.setdefault("stats", None)
st.session_state.setdefault("meta", None)
st.session_state.setdefault("chat", [])
st.session_state.setdefault("upload_name", None)

client = get_client()
has_data = st.session_state["df"] is not None and not st.session_state["df"].empty


# ----------------------------------------------------------------- sidebar

with st.sidebar:
    st.markdown(f"## 💸 {APP_NAME}")
    st.caption("UPI spending, explained — then ask it anything.")

    if has_data:
        df: pd.DataFrame = st.session_state["df"]
        stats: dict = st.session_state["stats"] or {}
        source = str(df["source"].iloc[0]).upper() if not df.empty else "—"
        first, last = df["date"].min(), df["date"].max()
        st.markdown(
            f"**Dataset**  \n"
            f"`{source}` · {len(df):,} transactions  \n"
            f"{first:%d %b %Y} → {last:%d %b %Y}"
        )
        st.caption(
            f"Categorized: {stats.get('rules', 0):,} rules · {stats.get('fallback', 0):,} P2P · "
            f"{stats.get('cache', 0):,} cache · {stats.get('llm', 0):,} AI · "
            f"{stats.get('other', 0):,} other"
        )
        st.session_state["exclude_transfers"] = st.checkbox(
            "Exclude P2P transfers from spending", value=False
        )
        if st.button("Start over", width="stretch"):
            reset_data()
            st.rerun()
    else:
        st.info("Load the sample data or upload a statement to begin.")

    with st.expander("About & privacy"):
        st.markdown(
            "Statements are parsed **in memory** and never stored. If an AI key is "
            "configured, only cleaned merchant names (never amounts, dates or account "
            "details) are sent for categorisation. The code is open source — verify it."
        )

    st.caption(f"v{APP_VERSION} · built by {AUTHOR} · MIT License")


# ---------------------------------------------------------------- landing

if not has_data:
    st.markdown(f'<div class="sp-hero">💸 {APP_NAME}</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="sp-sub">Where did your money go? Upload a UPI statement and find out '
        "in ten seconds.</div>",
        unsafe_allow_html=True,
    )

    col_a, col_b, col_c = st.columns(3)
    col_a.markdown(
        '<div class="sp-card"><h4>📊 Auto-categorized</h4>'
        "<p>Every transaction sorted into food, transport, subscriptions and more — "
        "no spreadsheet work.</p></div>",
        unsafe_allow_html=True,
    )
    col_b.markdown(
        '<div class="sp-card"><h4>🔍 Hidden charges</h4>'
        "<p>Recurring subscriptions, fee leaks and the months that were way above "
        "your normal.</p></div>",
        unsafe_allow_html=True,
    )
    col_c.markdown(
        '<div class="sp-card"><h4>💬 Ask anything</h4>'
        "<p>“How much did I spend on Swiggy in September?” — answered with a guarded "
        "SQL copilot.</p></div>",
        unsafe_allow_html=True,
    )

    st.write("")
    left, right = st.columns([1, 1])
    with left:
        if st.button("▶  Try it with sample data", type="primary", key="load_sample"):
            load_sample()
            st.rerun()
        st.caption("No statement needed — loads 6 months of realistic demo data.")
    with right:
        uploaded = st.file_uploader(
            "Or upload your statement (PDF or CSV)",
            type=["pdf", "csv", "txt", "tsv"],
            key="uploader",
        )
        st.caption("Works with Google Pay / PhonePe statement exports and bank CSVs.")

    if uploaded is not None and st.session_state.get("upload_name") != uploaded.name:
        try:
            with st.spinner("Reading statement…"):
                frame, meta = parse_statement(uploaded, uploaded.name)
            apply_data(frame, meta)
            st.session_state["upload_name"] = uploaded.name
            st.rerun()
        except ParseError as exc:
            st.error(f"Couldn't parse this statement: {exc}")
        except Exception as exc:  # noqa: BLE001 — show a friendly message, not a traceback
            st.error(f"Unexpected error while parsing: {exc}")

    st.divider()
    st.caption(
        "🔒 Statements are processed in memory and never stored or uploaded anywhere. "
        "The parser runs locally in this app."
    )
    st.stop()


# -------------------------------------------------------------- dashboard

df = st.session_state["df"]
stats = st.session_state["stats"] or {}
include_transfers = not st.session_state.get("exclude_transfers", False)
rows = analytics.spend_rows(df, include_transfers)

st.markdown(f'<div class="sp-hero">{APP_NAME}</div>', unsafe_allow_html=True)
st.markdown(
    f'<span class="sp-badge">{str(df["source"].iloc[0]).upper()}</span>'
    f'<span class="sp-badge">{len(df):,} transactions</span>'
    f'<span class="sp-badge">categorized {stats.get("total", 0):,}</span>',
    unsafe_allow_html=True,
)
st.write("")

if rows.empty:
    st.warning("No debit transactions found with the current filter.")
    st.stop()

tab_overview, tab_trends, tab_merchants, tab_subs, tab_ask, tab_export = st.tabs(
    [
        "📊 Overview",
        "📈 Trends",
        "🏪 Merchants",
        "🔁 Subscriptions",
        "💬 Ask AI",
        "⬇️ Export",
    ]
)

kpis = analytics.overview_kpis(df, include_transfers)

with tab_overview:
    st.markdown(
        f"""
        <div class="stat-strip">
          <div class="stat" title="All debits in range">
            <div class="stat-label">Total spent</div>
            <div class="stat-value">{charts.inr_compact(kpis['total_spend'])}</div>
          </div>
          <div class="stat" title="Across {kpis['months']} month(s)">
            <div class="stat-label">Monthly average</div>
            <div class="stat-value">{charts.inr_compact(kpis['average_monthly'])}</div>
          </div>
          <div class="stat" title="{money(kpis['top_category_amount'])} in total">
            <div class="stat-label">Biggest category</div>
            <div class="stat-value">{kpis['top_category']}</div>
          </div>
          <div class="stat" title="{kpis['recurring_count']} subscriptions detected">
            <div class="stat-label">Recurring / month</div>
            <div class="stat-value">{charts.inr_compact(kpis['recurring_monthly'])}</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    monthly = analytics.monthly_spend(rows)
    breakdown = analytics.category_breakdown(rows)
    chart_left, chart_right = st.columns([1.2, 1])
    with chart_left:
        figure = charts.monthly_spend_figure(monthly)
        if figure:
            st.plotly_chart(figure, width="stretch", key="chart_overview_monthly")
    with chart_right:
        figure = charts.category_figure(breakdown)
        if figure:
            st.plotly_chart(figure, width="stretch", key="chart_overview_category")

    insight = analytics.headline_insight(rows)
    if insight:
        st.info(f"💡 {insight}")
    st.caption(
        f"🍽️ Food & dining (delivery + eating out) was {kpis['food_dining_share'] * 100:.0f}% "
        "of your spending this period."
    )

with tab_trends:
    summary = analytics.monthly_summary(df)
    if not summary.empty:
        display = money_frame(summary, ["spend", "credits"])
        display = display.rename(
            columns={
                "month": "Month",
                "spend": "Spent",
                "credits": "Received",
                "transactions": "Transactions",
            }
        )
        st.dataframe(display, hide_index=True)
        figure = charts.monthly_spend_figure(analytics.monthly_spend(rows))
        if figure:
            st.plotly_chart(figure, width="stretch", key="chart_trends_monthly")

    anomalies = analytics.find_anomalies(rows)
    if anomalies:
        st.subheader("Unusual months")
        for entry in anomalies:
            st.warning(
                f"**{entry['month']}** — {money(entry['spend'])} spent, "
                f"{entry['multiple']:.1f}× your average. Driven by "
                f"{entry['driver']} ({money(entry['driver_amount'])})."
            )
    else:
        st.caption("No unusual months detected in this range.")

    risers = analytics.category_breakdown(rows)
    risers = risers[risers["change_pct"].notna()].sort_values("change_pct", ascending=False)
    if not risers.empty:
        st.subheader("Category momentum (latest month vs previous)")
        mover_columns = st.columns(min(3, len(risers)))
        for column, (_, entry) in zip(mover_columns, risers.head(3).iterrows()):
            column.metric(
                entry["category"],
                money(entry["total"]),
                delta=f"{entry['change_pct']:+.0f}% MoM",
            )

with tab_merchants:
    merchants = analytics.top_merchants(rows, count=15)
    search = st.text_input("Search a merchant", placeholder="e.g. swiggy")
    to_show = merchants
    if search:
        to_show = merchants[merchants["merchant"].str.contains(search, case=False, na=False)]
    if not to_show.empty:
        display = money_frame(to_show, ["total", "average"])
        display = display.rename(
            columns={
                "merchant": "Merchant",
                "category": "Category",
                "total": "Total",
                "transactions": "Txns",
                "average": "Average",
            }
        )
        st.dataframe(display, hide_index=True)
        figure = charts.merchants_figure(to_show)
        if figure:
            st.plotly_chart(figure, width="stretch", key="chart_merchants")
    else:
        st.caption("No merchants match that search.")

with tab_subs:
    subscriptions = analytics.detect_subscriptions(df)
    if subscriptions.empty:
        st.caption(
            "No recurring charges detected yet. Detection needs at least three charges "
            "with a roughly monthly cadence and a stable amount."
        )
    else:
        total_monthly = subscriptions["estimated_monthly"].sum()
        st.metric("Estimated recurring cost", f"{money(total_monthly)} / month")
        display = money_frame(subscriptions, ["average", "estimated_monthly"])
        display = display.rename(
            columns={
                "merchant": "Merchant",
                "category": "Category",
                "average": "Avg amount",
                "charges": "Charges",
                "months": "Months",
                "estimated_monthly": "Per month",
            }
        )
        st.dataframe(display, hide_index=True)
        st.caption(
            "Detected from cadence (roughly monthly) and stable amounts — not from a "
            "hardcoded list of services."
        )

with tab_ask:
    if not client.available():
        st.info(
            "**Copilot is off.** Add a free Gemini API key to enable plain-English "
            "questions — see the README (2-minute setup). Everything else works without it."
        )
    suggestions = [
        "How much did I spend on food delivery?",
        "What are my top 5 merchants?",
        "How much did I spend per month?",
        "Which subscriptions am I paying for?",
    ]
    suggestion_columns = st.columns(2)
    pending = None
    for index, suggestion in enumerate(suggestions):
        if suggestion_columns[index % 2].button(
            suggestion, key=f"suggestion_{index}", width="stretch"
        ):
            pending = suggestion

    for message_index, message in enumerate(st.session_state["chat"]):
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            if message.get("sql"):
                with st.expander("Generated SQL"):
                    st.code(message["sql"], language="sql")
            if message.get("table") is not None:
                table: pd.DataFrame = message["table"]
                if table.shape == (1, 1) and pd.api.types.is_numeric_dtype(table.iloc[:, 0]):
                    st.metric(
                        str(table.columns[0]).replace("_", " ").title(),
                        f"₹{table.iloc[0, 0]:,.2f}",
                    )
                else:
                    figure = charts.result_figure(table)
                    if figure:
                        st.plotly_chart(
                            figure, width="stretch", key=f"chart_history_{message_index}"
                        )
                    st.dataframe(table, hide_index=True)

    question = st.chat_input("Ask about your spending…", disabled=not client.available())
    question = pending or question

    if question:
        st.session_state["chat"].append({"role": "user", "content": question})
        with st.chat_message("user"):
            st.markdown(question)
        with st.chat_message("assistant"):
            with st.spinner("Thinking…"):
                result = copilot.answer_question(question, df, client)
            if result.error:
                st.error(result.error)
                st.session_state["chat"].append(
                    {"role": "assistant", "content": f"⚠️ {result.error}"}
                )
            else:
                st.markdown(result.answer)
                figure = charts.result_figure(result.table) if result.table is not None else None
                if result.table is not None:
                    if result.table.shape == (1, 1) and pd.api.types.is_numeric_dtype(
                        result.table.iloc[:, 0]
                    ):
                        st.metric(
                            str(result.table.columns[0]).replace("_", " ").title(),
                            f"₹{result.table.iloc[0, 0]:,.2f}",
                        )
                    else:
                        if figure:
                            st.plotly_chart(figure, width="stretch", key="chart_chat_current")
                        st.dataframe(result.table, hide_index=True)
                if result.sql:
                    with st.expander("Generated SQL"):
                        st.code(result.sql, language="sql")
                st.session_state["chat"].append(
                    {
                        "role": "assistant",
                        "content": result.answer,
                        "sql": result.sql,
                        "table": result.table,
                    }
                )
        st.caption(
            "SQL is generated by AI and validated before running — read-only, single statement."
        )

with tab_export:
    cleaned = df.copy()
    summary = analytics.monthly_summary(df)
    export_columns = st.columns(2)
    export_columns[0].download_button(
        "⬇️ Cleaned transactions (CSV)",
        data=cleaned.to_csv(index=False).encode("utf-8"),
        file_name="spendlytics_transactions.csv",
        mime="text/csv",
        width="stretch",
    )
    export_columns[1].download_button(
        "⬇️ Monthly summary (CSV)",
        data=summary.to_csv(index=False).encode("utf-8"),
        file_name="spendlytics_monthly_summary.csv",
        mime="text/csv",
        width="stretch",
    )
    st.subheader("Data preview")
    preview = money_frame(cleaned, ["amount"])
    st.dataframe(preview, hide_index=True, height=320)
    with st.expander("Data dictionary"):
        st.markdown(
            "| Column | Meaning |\n|---|---|\n"
            "| date | Transaction date (normalised) |\n"
            "| description | Raw narration from the statement |\n"
            "| merchant | Cleaned merchant name |\n"
            "| amount | Absolute value in ₹ |\n"
            "| direction | debit (spent) or credit (received) |\n"
            "| category | Assigned spending category |\n"
            "| source | Which parser produced the row |"
        )

st.caption(f"{APP_NAME} v{APP_VERSION} · built by {AUTHOR} · MIT License")
