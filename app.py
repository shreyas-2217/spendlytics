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
APP_VERSION = "0.2.0"

st.set_page_config(
    page_title=f"{APP_NAME} · UPI spending, explained",
    page_icon="💸",
    layout="wide",
    initial_sidebar_state="expanded",
)

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=Instrument+Serif:ital@0;1&family=Manrope:wght@400;500;600;700;800&display=swap');

:root {
    --paper: #F7F6F2;
    --surface: #FFFFFF;
    --ink: #171A21;
    --muted: #5F6672;
    --line: #E5E2D9;
    --accent: #C1442E;
    --accent-ink: #9E3524;
    --mono: 'IBM Plex Mono', 'SFMono-Regular', Consolas, monospace;
}

html, body {background: var(--paper);}
.stApp {background: var(--paper); font-family: 'Manrope', 'Segoe UI', sans-serif;}
[data-testid="stHeader"] {background: transparent;}
[data-testid="stToolbar"] {display: none;}
[data-testid="stSidebar"] {background: #F2F0E9; border-right: 1px solid var(--line);}
.block-container {max-width: 1160px; padding-top: 3.6rem; padding-bottom: 3rem;}
h1, h2, h3, h4 {font-family: 'Manrope', 'Segoe UI', sans-serif !important;
    letter-spacing: -0.01em; color: var(--ink);}

/* icon glyphs keep their own font */
[data-testid="stIconMaterial"], .material-symbols-rounded {
    font-family: 'Material Symbols Rounded' !important;
}

/* heading anchor links are Streamlit chrome, not product */
[data-testid="stHeaderActionElements"] {display: none !important;}

/* ---------------------------------------------------------- landing */
.sp-eyebrow {font-family: var(--mono); font-size: 0.72rem; letter-spacing: 0.14em;
    text-transform: uppercase; color: var(--accent); margin-bottom: 0.9rem;}
.sp-display {font-family: 'Instrument Serif', Georgia, serif !important; font-weight: 400;
    font-size: clamp(2.1rem, 4.2vw, 3.3rem); line-height: 1.06; color: var(--ink);
    margin: 0 0 1rem 0; letter-spacing: -0.01em;}
.sp-display em {font-style: italic;}
.sp-lede {font-size: 1.02rem; color: var(--muted); max-width: 34rem; line-height: 1.6;
    margin: 0 0 1rem 0;}
.sp-lede-sm {font-size: 0.92rem; color: var(--muted); line-height: 1.55; margin: 0 0 0.9rem 0;}
.sp-trust {font-family: var(--mono); font-size: 0.74rem; letter-spacing: 0.02em;
    color: var(--muted);}
.sp-card-title {font-weight: 700; font-size: 1.02rem; color: var(--ink); margin-bottom: 0.35rem;}
.sp-or {display: flex; align-items: center; gap: 12px; color: var(--muted); font-size: 0.72rem;
    font-family: var(--mono); letter-spacing: 0.08em; text-transform: uppercase;
    margin: 0.9rem 0 0.7rem 0;}
.sp-or::before, .sp-or::after {content: ""; height: 1px; background: var(--line); flex: 1;}
.sp-steps {display: grid; grid-template-columns: repeat(auto-fit, minmax(230px, 1fr));
    gap: 26px; border-top: 1px solid var(--line); margin-top: 2.4rem; padding-top: 1.4rem;}
.sp-step-no {font-family: var(--mono); font-size: 0.72rem; color: var(--accent);
    letter-spacing: 0.1em;}
.sp-step-title {font-weight: 700; font-size: 0.98rem; margin: 0.35rem 0 0.3rem 0;
    color: var(--ink);}
.sp-step p {font-size: 0.88rem; color: var(--muted); line-height: 1.55; margin: 0;}
.sp-foot {font-family: var(--mono); font-size: 0.7rem; color: #8B8B80; letter-spacing: 0.02em;
    margin-top: 2.6rem;}

/* -------------------------------------------------------- dashboard */
.sp-head {display: flex; flex-wrap: wrap; align-items: flex-end; justify-content: space-between;
    gap: 10px; border-bottom: 1px solid var(--line); padding-bottom: 14px;
    margin-bottom: 0.9rem;}
.sp-wordmark {font-size: 1.35rem; font-weight: 800; letter-spacing: -0.02em; color: var(--ink);}
.sp-head-sub {font-size: 0.8rem; color: var(--muted); margin-top: 1px;}
.sp-chips {display: flex; flex-wrap: wrap; gap: 8px;}
.sp-chip {font-family: var(--mono); font-size: 0.7rem; letter-spacing: 0.05em;
    text-transform: uppercase; color: #3E4450; background: var(--surface);
    border: 1px solid var(--line); border-radius: 999px; padding: 4px 11px;}
.sp-chip-accent {color: var(--accent); border-color: #EBD3CD; background: #FDF3F0;}
.stat-strip {display: grid; grid-template-columns: repeat(auto-fit, minmax(205px, 1fr));
    gap: 10px; margin-bottom: 0.6rem;}
.stat {background: var(--surface); border: 1px solid var(--line); border-radius: 14px;
    padding: 15px 18px;}
.stat-label {font-family: var(--mono); font-size: 0.68rem; text-transform: uppercase;
    letter-spacing: 0.08em; color: var(--muted);}
.stat-value {font-family: var(--mono); font-size: 1.45rem; font-weight: 600; color: var(--ink);
    line-height: 1.35; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;}
.sp-callout {background: #FFFDF6; border: 1px solid var(--line);
    border-left: 3px solid var(--accent);
    border-radius: 12px; padding: 14px 18px; font-size: 0.95rem; color: var(--ink);
    line-height: 1.55; margin-top: 0.3rem;}
.sp-callout-k {display: block; font-family: var(--mono); font-size: 0.66rem;
    letter-spacing: 0.1em; text-transform: uppercase; color: var(--accent); margin-bottom: 4px;}
.sp-side-label {font-family: var(--mono); font-size: 0.66rem; letter-spacing: 0.1em;
    text-transform: uppercase; color: var(--muted); margin: 0.6rem 0 0.3rem 0;}
.sp-side-line {font-size: 0.82rem; color: var(--muted); line-height: 1.6;}
.sp-side-line b {color: var(--ink); font-family: var(--mono); font-weight: 600;}

/* -------------------------------------------------- native widgets */
div[data-testid="stMetric"] {background: var(--surface); border: 1px solid var(--line);
    border-radius: 14px; padding: 15px 18px;}
div[data-testid="stMetricLabel"] {font-family: var(--mono) !important; text-transform: uppercase;
    letter-spacing: 0.08em;}
div[data-testid="stMetricValue"] {font-family: var(--mono); font-size: 1.35rem;}
div[data-testid="stVerticalBlockBorderWrapper"] {background: var(--surface);
    border-color: var(--line) !important; border-radius: 16px;}
.stButton > button, .stDownloadButton > button {border-radius: 10px; border: 1px solid #D9D5C9;
    background: var(--surface); color: var(--ink); font-weight: 600;}
.stButton > button:hover, .stDownloadButton > button:hover {
    border-color: var(--ink); color: var(--ink);}
.stButton > button[kind="primary"], button[data-testid="stBaseButton-primary"] {
    background: var(--accent); border-color: var(--accent); color: #FFFFFF;}
.stButton > button[kind="primary"]:hover, button[data-testid="stBaseButton-primary"]:hover {
    background: var(--accent-ink); border-color: var(--accent-ink); color: #FFFFFF;}
.stTabs [data-baseweb="tab-list"] {gap: 2px; border-bottom: 1px solid var(--line);}
.stTabs [data-baseweb="tab"] {font-weight: 600; font-size: 0.92rem; color: var(--muted);}
.stTabs [aria-selected="true"] {color: var(--accent) !important;}
.stTabs [data-baseweb="tab-highlight"] {background-color: var(--accent);}
[data-testid="stFileUploaderDropzone"] {background: #FBFAF5; border: 1.5px dashed #CFCBBE;
    border-radius: 12px;}
[data-testid="stFileUploaderDropzone"] button {border-radius: 8px; border-color: #D9D5C9;}
div[data-testid="stAlert"] {border-radius: 12px;}
div[data-testid="stChatMessage"] {background: var(--surface); border: 1px solid var(--line);
    border-radius: 14px;}
[data-testid="stChatInput"] textarea {font-family: 'Manrope', sans-serif;}
code, pre, .stCode {font-family: var(--mono);}
div[data-testid="stExpander"] details {border-radius: 12px; border-color: var(--line);}
[data-testid="stWidgetLabel"] p {font-weight: 600; font-size: 0.88rem;}

@keyframes sp-rise {from {opacity: 0; transform: translateY(8px);}
    to {opacity: 1; transform: none;}}
.sp-eyebrow, .sp-display, .sp-lede, .sp-trust {animation: sp-rise 0.5s ease-out both;}
.sp-lede {animation-delay: 0.05s;}
.sp-steps {animation: sp-rise 0.6s ease-out 0.1s both;}
@media (prefers-reduced-motion: reduce) {
    .sp-eyebrow, .sp-display, .sp-lede, .sp-trust, .sp-steps {animation: none;}
}
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


def get_client() -> LLMClient:
    """A fresh client per run so key changes apply without a process restart."""
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
    for key in ("df", "stats", "meta", "chat", "upload_name", "uploader"):
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
    st.markdown('<div class="sp-wordmark" style="font-size:1.2rem;">Spendlytics</div>',
                unsafe_allow_html=True)
    st.caption("UPI spending, explained — then ask it anything.")

    if has_data:
        df: pd.DataFrame = st.session_state["df"]
        stats: dict = st.session_state["stats"] or {}
        source = str(df["source"].iloc[0]).upper()
        first, last = df["date"].min(), df["date"].max()
        st.markdown('<div class="sp-side-label">Statement</div>', unsafe_allow_html=True)
        st.markdown(
            f'<div class="sp-side-line"><b>{source}</b> · {len(df):,} transactions<br>'
            f"{first:%d %b %Y} → {last:%d %b %Y}</div>",
            unsafe_allow_html=True,
        )
        identified = stats.get("total", 0) - stats.get("other", 0)
        matched = f"<b>{identified:,}</b> of {stats.get('total', 0):,} recognized"
        if stats.get("other"):
            matched += f'<br><b>{stats["other"]:,}</b> left as Other'
        st.markdown('<div class="sp-side-label">Merchants</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="sp-side-line">{matched}</div>', unsafe_allow_html=True)
        st.write("")
        st.session_state["include_transfers"] = st.checkbox(
            "Include transfers to people", value=True
        )
        st.button("Start over", width="stretch", on_click=reset_data)
    else:
        st.markdown(
            '<div class="sp-side-line">Load the demo statement or add your own to begin.</div>',
            unsafe_allow_html=True,
        )

    with st.expander("Privacy & data"):
        st.markdown(
            "Your statement is processed in memory in this session and never stored. "
            "Merchant names may be sent to an AI service for categorization — never "
            "amounts, dates or account numbers. Chat questions send only your question "
            "and the column names."
        )
        if st.session_state.get("stats"):
            split = st.session_state["stats"]
            st.caption(
                f"This statement: {split.get('rules', 0):,} categorized by built-in rules, "
                f"{split.get('cache', 0):,} remembered from earlier, "
                f"{split.get('llm', 0):,} by AI, "
                f"{split.get('fallback', 0):,} matched as person-to-person."
            )

    st.caption(f"{APP_NAME} v{APP_VERSION} · MIT License")


# ----------------------------------------------------------------- landing

if not has_data:
    left, right = st.columns([1.08, 0.92], gap="large")
    with left:
        st.markdown(
            """
            <div class="sp-eyebrow">UPI statement analyser</div>
            <h1 class="sp-display">Your UPI history,<br>finally <em>in order</em>.</h1>
            <p class="sp-lede">Drop a Google&nbsp;Pay, PhonePe or bank statement. See where the
            money went, catch the subscriptions you forgot, and ask plain-English questions
            about your own spending.</p>
            <p class="sp-trust">No sign-up · nothing stored · reads the export you already have</p>
            """,
            unsafe_allow_html=True,
        )
    with right:
        with st.container(border=True):
            st.markdown('<div class="sp-card-title">Add your statement</div>',
                        unsafe_allow_html=True)
            uploaded = st.file_uploader(
                "Statement file",
                type=["pdf", "csv", "txt", "tsv"],
                key="uploader",
                label_visibility="collapsed",
            )
            st.caption("PDF or CSV — from any bank or UPI app.")
            if uploaded is not None and st.session_state.get("upload_name") != uploaded.name:
                try:
                    with st.spinner("Reading statement…"):
                        frame, meta = parse_statement(uploaded, uploaded.name)
                    apply_data(frame, meta)
                    st.session_state["upload_name"] = uploaded.name
                    st.rerun()
                except ParseError as exc:
                    st.error(f"Couldn't read this statement: {exc}")
                except Exception as exc:  # noqa: BLE001 — friendly message, not a traceback
                    st.error(f"Something went wrong while reading the file: {exc}")
            st.markdown('<div class="sp-or">or</div>', unsafe_allow_html=True)
            if st.button(
                "Try it with the demo statement",
                type="primary",
                width="stretch",
                key="load_sample",
            ):
                load_sample()
                st.rerun()
            st.caption("Six months of sample data. Nothing is uploaded.")

    st.markdown(
        f"""
        <div class="sp-steps">
          <div class="sp-step">
            <div class="sp-step-no">01</div>
            <div class="sp-step-title">Export it</div>
            <p>Google&nbsp;Pay → profile → Transaction statement. PhonePe → profile →
            Transaction history. Any bank → net banking → download CSV or PDF.</p>
          </div>
          <div class="sp-step">
            <div class="sp-step-no">02</div>
            <div class="sp-step-title">Drop it here</div>
            <p>PDF and CSV both work — any bank, any statement, no preparation
            needed.</p>
          </div>
          <div class="sp-step">
            <div class="sp-step-no">03</div>
            <div class="sp-step-title">Read the report</div>
            <p>See where it went, what you're still paying for, and which months stood
            out — then ask anything.</p>
          </div>
        </div>
        <div class="sp-foot">Spendlytics v{APP_VERSION} · Statements are processed in
        memory, never stored</div>
        """,
        unsafe_allow_html=True,
    )
    st.stop()


# -------------------------------------------------------------- dashboard

df = st.session_state["df"]
include_transfers = bool(st.session_state.get("include_transfers", True))
rows = analytics.spend_rows(df, include_transfers)

st.markdown(
    f"""
    <div class="sp-head">
      <div>
        <div class="sp-wordmark">{APP_NAME}</div>
        <div class="sp-head-sub">UPI spending, explained — then ask it anything</div>
      </div>
      <div class="sp-chips">
        <span class="sp-chip sp-chip-accent">{str(df["source"].iloc[0]).upper()}</span>
        <span class="sp-chip">{len(df):,} transactions</span>
        <span class="sp-chip">{df["date"].min():%d %b %Y} – {df["date"].max():%d %b %Y}</span>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)

if rows.empty:
    st.warning("No spending transactions match the current settings.")
    st.stop()

tab_overview, tab_trends, tab_merchants, tab_subs, tab_ask, tab_export = st.tabs(
    [
        "Overview",
        "Trends",
        "Merchants",
        "Subscriptions",
        "Ask AI",
        "Export",
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
        st.markdown(
            f'<div class="sp-callout"><span class="sp-callout-k">Insight</span>'
            f"{insight}</div>",
            unsafe_allow_html=True,
        )
    st.caption(
        f"Food & dining (delivery + eating out) was {kpis['food_dining_share'] * 100:.0f}% "
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
        st.subheader("What changed — latest month vs previous")
        mover_columns = st.columns(min(3, len(risers)))
        for column, (_, entry) in zip(mover_columns, risers.head(3).iterrows()):
            column.metric(
                entry["category"],
                money(entry["total"]),
                delta=f"{entry['change_pct']:+.0f}%",
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
            "No recurring charges yet. They appear here once the same amount repeats "
            "every month or so."
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
        st.caption("Found from their billing rhythm: roughly monthly, similar amounts.")

with tab_ask:
    st.markdown(
        '<p class="sp-lede-sm">Ask about totals, categories, merchants or months — '
        "plain English works.</p>",
        unsafe_allow_html=True,
    )
    if not client.available():
        st.markdown(
            '<div class="sp-callout"><span class="sp-callout-k">Ask AI is off</span>'
            "Questions need an AI key. Add a free Gemini API key to switch this on — "
            "everything else works without it.</div>",
            unsafe_allow_html=True,
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
                with st.expander("How this was calculated"):
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
                    with st.expander("How this was calculated"):
                        st.code(result.sql, language="sql")
                st.session_state["chat"].append(
                    {
                        "role": "assistant",
                        "content": result.answer,
                        "sql": result.sql,
                        "table": result.table,
                    }
                )
        st.caption("AI answers can be wrong — double-check anything important.")

with tab_export:
    cleaned = df.copy()
    summary = analytics.monthly_summary(df)
    export_columns = st.columns(2)
    export_columns[0].download_button(
        "Download all transactions (CSV)",
        data=cleaned.to_csv(index=False).encode("utf-8"),
        file_name="spendlytics_transactions.csv",
        mime="text/csv",
        width="stretch",
    )
    export_columns[1].download_button(
        "Download monthly summary (CSV)",
        data=summary.to_csv(index=False).encode("utf-8"),
        file_name="spendlytics_monthly_summary.csv",
        mime="text/csv",
        width="stretch",
    )
    st.subheader("Preview")
    preview = money_frame(cleaned, ["amount"])
    st.dataframe(preview, hide_index=True, height=320)
    with st.expander("About these columns"):
        st.markdown(
            "| Column | Meaning |\n|---|---|\n"
            "| date | Transaction date |\n"
            "| description | Original text from the statement |\n"
            "| merchant | Cleaned merchant name |\n"
            "| amount | Amount in ₹ |\n"
            "| direction | Spent or received |\n"
            "| category | Spending category |\n"
            "| source | File this row came from |"
        )

st.caption(f"{APP_NAME} v{APP_VERSION} · MIT License")
