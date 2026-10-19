"""Tests for the parsing helpers: amounts, dates, merchants, column mapping."""

from datetime import datetime

from src.parsers.base import (
    clean_merchant,
    detect_columns,
    parse_amount,
    parse_date,
    rows_to_transactions,
)
from src.parsers.csv_statement import parse_csv


class TestParseAmount:
    def test_plain_number(self):
        assert parse_amount("1234") == 1234.0

    def test_rupee_sign_and_commas(self):
        assert parse_amount("₹1,234.56") == 1234.56

    def test_parentheses_mean_negative(self):
        assert parse_amount("(500)") == -500.0

    def test_ignores_dr_suffix(self):
        assert parse_amount("349.00 Dr") == 349.0

    def test_garbage_returns_none(self):
        assert parse_amount("abc") is None
        assert parse_amount("") is None
        assert parse_amount(None) is None


class TestParseDate:
    def test_day_first(self):
        assert parse_date("12/09/2026") == datetime(2026, 9, 12)

    def test_iso(self):
        assert parse_date("2026-09-12") == datetime(2026, 9, 12)

    def test_month_name(self):
        assert parse_date("12 Sep 2026") == datetime(2026, 9, 12)

    def test_reference_number_is_not_a_date(self):
        assert parse_date("412345678901") is None

    def test_garbage_returns_none(self):
        assert parse_date("hello") is None


class TestCleanMerchant:
    def test_upi_narration(self):
        assert clean_merchant("UPI/DR/412345678901/RAZ*SWIGGY/YESB/swiggy@ybl") == "Swiggy"

    def test_star_prefix(self):
        assert clean_merchant("RAZ*SWIGGY") == "Swiggy"

    def test_person_transfer(self):
        assert clean_merchant("UPI/P2A/412345678901/Aarav Sharma/aarav@ybl") == "Aarav Sharma"


class TestDetectColumns:
    def test_header_table(self):
        rows = [
            ["Date", "Description", "Amount"],
            ["12/09/2026", "UPI/DR/1/RAZ*SWIGGY/swiggy@ybl", "349.00"],
            ["13/09/2026", "UPI/DR/2/UBER/uber@ybl", "120.50"],
        ]
        mapping = detect_columns(rows)
        assert (mapping.date, mapping.description, mapping.amount) == (0, 1, 2)
        assert mapping.header_row == 0

    def test_headerless_content_detection(self):
        rows = [
            ["12/09/2026", "RAZ*SWIGGY", "349.00"],
            ["13/09/2026", "UBER", "120.50"],
            ["14/09/2026", "ZOMATO", "210.00"],
        ]
        mapping = detect_columns(rows)
        assert mapping.date == 0
        assert mapping.description == 1
        assert mapping.amount == 2


class TestRowsToTransactions:
    def test_negative_amount_is_debit(self):
        rows = [["12/09/2026", "RAZ*SWIGGY", "-349.00"]]
        mapping = detect_columns(rows)
        frame = rows_to_transactions(rows, mapping)
        assert frame.iloc[0]["direction"] == "debit"
        assert frame.iloc[0]["amount"] == 349.0

    def test_debit_and_credit_columns(self):
        rows = [
            ["Date", "Narration", "Debit", "Credit"],
            ["12/09/2026", "Uber ride", "120.50", ""],
            ["13/09/2026", "Refund from Swiggy", "", "150.00"],
        ]
        mapping = detect_columns(rows)
        frame = rows_to_transactions(rows, mapping)
        assert len(frame) == 2
        assert set(frame["direction"]) == {"debit", "credit"}
        assert frame["amount"].sum() == 270.5


class TestCsvEndToEnd:
    def test_parse_csv_file(self, tmp_path):
        content = (
            "Date,Description,Amount\n"
            "12/09/2026,UPI/DR/1/RAZ*SWIGGY/swiggy@ybl,349.00\n"
            "13/09/2026,UPI/DR/2/UBER/uber@ybl,-120.50\n"
        )
        path = tmp_path / "statement.csv"
        path.write_text(content, encoding="utf-8")
        frame, meta = parse_csv(str(path))
        assert len(frame) == 2
        assert meta["delimiter"] == ","
        assert frame["amount"].sum() == 469.5
