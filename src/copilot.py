"""Ask-your-money copilot: natural language -> guarded DuckDB SQL -> answer.

Guardrails
----------
- Only a single read-only ``SELECT`` / ``WITH`` statement is accepted.
- Dangerous keywords (DDL, DML, ATTACH, PRAGMA, ...) are rejected.
- A ``LIMIT`` is appended when missing, so a runaway query cannot page the UI.
- The query runs against an in-memory DuckDB table that only exists for the
  duration of the request — nothing is persisted.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import duckdb
import pandas as pd

from src.llm import LLMClient

TABLE = "transactions"

SYSTEM_PROMPT = (
    "You are a careful data analyst for a personal-finance app. "
    f"You write DuckDB SQL against a single table: {TABLE}(date DATE, description VARCHAR, "
    "merchant VARCHAR, amount DOUBLE, direction VARCHAR, category VARCHAR). "
    "direction is 'debit' (money spent) or 'credit'. amount is always positive. "
    "Rules: reply with ONE read-only SELECT statement, no markdown code fences, no comments. "
    "Never use INSERT/UPDATE/DELETE/CREATE/DROP/ALTER/ATTACH/COPY/PRAGMA. "
    "Use ILIKE for case-insensitive text matching. Round money to 2 decimals with clear aliases. "
    "If the question truly cannot be answered with this schema, reply with exactly: CANNOT_ANSWER"
)

EXAMPLES: list[tuple[str, str]] = [
    (
        "How much did I spend in total?",
        "SELECT ROUND(SUM(amount), 2) AS total_spend FROM transactions WHERE direction = 'debit'",
    ),
    (
        "What are my top 5 merchants?",
        "SELECT merchant, ROUND(SUM(amount), 2) AS total FROM transactions "
        "WHERE direction = 'debit' GROUP BY merchant ORDER BY total DESC LIMIT 5",
    ),
    (
        "How much do I spend per month?",
        "SELECT strftime(date, '%Y-%m') AS month, ROUND(SUM(amount), 2) AS spend "
        "FROM transactions WHERE direction = 'debit' GROUP BY month ORDER BY month",
    ),
    (
        "How much went to food delivery?",
        "SELECT COUNT(*) AS orders, ROUND(SUM(amount), 2) AS spend FROM transactions "
        "WHERE category = 'Food Delivery'",
    ),
]

_FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|create|alter|attach|detach|copy|pragma|vacuum|export"
    r"|import|install|load|call|set|reset|raise)\b",
    re.I,
)
_FENCE = re.compile(r"^```[a-zA-Z]*\s*|\s*```$")


@dataclass
class AskResult:
    """Everything the UI needs to render one copilot answer."""

    question: str
    answer: str = ""
    sql: str | None = None
    table: pd.DataFrame | None = None
    error: str | None = None


def validate_sql(sql: str) -> tuple[bool, str]:
    """Return ``(True, cleaned_sql)`` or ``(False, reason)``.

    Only a single read-only SELECT (optionally a CTE) passes. A LIMIT is
    appended when the query does not already have one.
    """
    text = _FENCE.sub("", (sql or "").strip()).strip()
    if not text:
        return False, "The model returned an empty query."
    if "CANNOT_ANSWER" in text.upper():
        return False, "This question can't be answered from the transaction data."
    if ";" in text.rstrip(";"):
        return False, "Only a single statement is allowed."
    text = text.rstrip(";").strip()
    lowered = text.lower()
    if not (lowered.startswith("select") or lowered.startswith("with")):
        return False, "Only SELECT queries are allowed."
    forbidden = _FORBIDDEN.search(lowered)
    if forbidden:
        return False, f"Query contains a forbidden keyword: {forbidden.group(0)}"
    if not re.search(r"\blimit\b", lowered):
        text += " LIMIT 500"
    return True, text


def run_sql(sql: str, df: pd.DataFrame) -> pd.DataFrame:
    """Execute a validated query against an in-memory copy of the data."""
    connection = duckdb.connect()
    try:
        connection.register(TABLE, df)
        return connection.execute(sql).fetchdf()
    finally:
        connection.close()


def _generate_sql(question: str, client: LLMClient, feedback: str | None = None) -> str | None:
    prompt = "Examples:\n" + "\n".join(f"Q: {q}\nSQL: {s}" for q, s in EXAMPLES)
    prompt += f"\n\nQuestion: {question}\nSQL:"
    if feedback:
        prompt += (
            f"\n\nYour previous attempt failed with: {feedback}\n"
            "Fix it and return only the SQL."
        )
    return client.complete(SYSTEM_PROMPT, prompt, temperature=0)


def _narrate(question: str, sql: str, result: pd.DataFrame, client: LLMClient) -> str:
    preview = result.head(20).to_csv(index=False)
    prompt = (
        f"Question: {question}\nSQL: {sql}\nResult (CSV, first rows):\n{preview}\n\n"
        "Answer the question in 1-3 short sentences using ₹ and Indian number formatting. "
        "Mention the key number(s). Do not include the SQL."
    )
    response = client.complete(
        "You explain query results for a personal finance dashboard.",
        prompt,
        temperature=0.2,
    )
    return (response or "").strip() or "Here is what I found:"


def answer_question(question: str, df: pd.DataFrame, client: LLMClient | None) -> AskResult:
    """Full copilot flow with one retry on failure."""
    result = AskResult(question=question)
    if client is None or not client.available():
        result.error = (
            "The copilot needs a free LLM API key — add one in .streamlit/secrets.toml and restart."
        )
        return result

    last_feedback: str | None = None
    for _ in range(2):  # one retry with feedback
        sql = _generate_sql(question, client, feedback=last_feedback)
        if sql is None:
            result.error = client.last_error or "The model could not be reached."
            return result
        ok, detail = validate_sql(sql)
        if not ok:
            last_feedback = detail
            result.sql = sql
            continue
        result.sql = detail
        try:
            table = run_sql(detail, df)
        except Exception as exc:  # noqa: BLE001 - surface query errors to the retry loop
            last_feedback = str(exc)
            continue
        result.table = table
        result.answer = _narrate(question, detail, table, client)
        return result

    result.error = last_feedback or "The model could not produce a valid query."
    return result
