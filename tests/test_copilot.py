"""Tests for the SQL copilot guardrails and execution."""

import pandas as pd

from src.copilot import run_sql, validate_sql


class TestValidateSql:
    def test_accepts_select_and_adds_limit(self):
        ok, sql = validate_sql("SELECT merchant FROM transactions")
        assert ok
        assert "LIMIT" in sql

    def test_keeps_existing_limit(self):
        ok, sql = validate_sql("SELECT 1 LIMIT 10")
        assert ok
        assert sql.lower().count("limit") == 1

    def test_rejects_delete(self):
        ok, _ = validate_sql("DELETE FROM transactions")
        assert not ok

    def test_rejects_multiple_statements(self):
        ok, _ = validate_sql("SELECT 1; DROP TABLE transactions")
        assert not ok

    def test_strips_markdown_fences(self):
        ok, sql = validate_sql("```sql\nSELECT COUNT(*) FROM transactions\n```")
        assert ok
        assert sql.startswith("SELECT")

    def test_cannot_answer(self):
        ok, _ = validate_sql("CANNOT_ANSWER")
        assert not ok


def test_run_sql_aggregates():
    frame = pd.DataFrame(
        {
            "date": pd.to_datetime(["2026-09-01", "2026-09-02"]),
            "description": ["a", "b"],
            "merchant": ["A", "B"],
            "amount": [10.0, 20.0],
            "direction": ["debit", "debit"],
            "category": ["Other", "Other"],
            "source": ["test", "test"],
        }
    )
    result = run_sql(
        "SELECT ROUND(SUM(amount), 2) AS total FROM transactions WHERE direction = 'debit'",
        frame,
    )
    assert result.iloc[0, 0] == 30.0
