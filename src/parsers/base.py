"""Format-agnostic helpers for turning statement tables into transactions.

Statement-specific code (CSV reader, PDF table extractor) produces raw rows —
lists of cell strings — and relies on these helpers to figure out which
column holds the date, which holds the amount, and so on.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import pandas as pd
from dateutil import parser as date_parser

from src.models import finalize_transactions


class ParseError(ValueError):
    """Raised when a statement cannot be turned into transactions."""


# ------------------------------------------------------------------ values


def parse_amount(value: Any) -> float | None:
    """Parse ``₹1,234.56``, ``1,234``, ``(500)`` or ``-500`` into a float.

    Returns ``None`` when the cell is not a number. Sign is preserved;
    callers normalise debit/credit semantics separately.
    """
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    negative = text.startswith("(") and text.endswith(")")
    if text.startswith("-") or text.endswith("-"):
        negative = True
    digits = re.sub(r"[^0-9.]", "", text)
    if digits in ("", ".") or digits.count(".") > 1:
        return None
    try:
        number = float(digits)
    except ValueError:
        return None
    return -number if negative else number


_DATE_FORMATS = (
    "%d/%m/%Y",
    "%d-%m-%Y",
    "%d.%m.%Y",
    "%d/%m/%y",
    "%d-%m-%y",
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%d %b %Y",
    "%d-%b-%Y",
    "%d %B %Y",
    "%b %d, %Y",
    "%B %d, %Y",
    "%d %b, %Y",
)


def parse_date(value: Any) -> datetime | None:
    """Parse the date formats commonly used in Indian bank/UPI statements."""
    if isinstance(value, datetime):
        return value
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if re.fullmatch(r"\d{7,}", text.replace(" ", "")):
        return None  # long digit runs are reference numbers, not dates
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    try:
        parsed = date_parser.parse(text, dayfirst=True)
    except (ValueError, OverflowError, TypeError):
        return None
    if 2000 <= parsed.year <= 2100:
        return parsed
    return None


_DEBIT_WORDS = re.compile(r"\b(dr|debit|withdrawal|withdrawn|wdl|paid|sent|out)\b", re.I)
_CREDIT_WORDS = re.compile(r"\b(cr|credit|deposit|received|refund)\b", re.I)


def direction_from_text(value: Any) -> str | None:
    """``'debit'``/``'credit'`` when the text says so, else ``None``."""
    if value is None:
        return None
    text = str(value)
    if _DEBIT_WORDS.search(text):
        return "debit"
    if _CREDIT_WORDS.search(text):
        return "credit"
    return None


# --------------------------------------------------------------- merchants

_VPA_RE = re.compile(r"@[a-z]+", re.I)
_REF_RE = re.compile(r"\b\d{5,}\b")
_NOISE_WORDS = re.compile(
    r"\b(upi|dr|cr|p2m|p2a|neft|imps|rtgs|ref|refno|txn|txnid|trf|transfer|payment|pay|pos"
    r"|purchase|to|from|via|at|bharat|bhim|collect|request|success|completed|debited|credited)\b",
    re.I,
)


def clean_merchant(raw: Any) -> str:
    """Best-effort cleanup of a messy UPI narration into a display name.

    ``"UPI/DR/412345678901/RAZ*SWIGGY/YESB/swiggy@ybl"`` -> ``"Swiggy"``
    """
    text = str(raw or "").strip()
    if not text:
        return "Unknown"
    segments = [segment.strip() for segment in re.split(r"[/|]", text) if segment.strip()]
    if segments:
        # Pick the segment with the most letters: reference numbers are digits
        # and bank codes like "YESB" are short noise.
        text = max(segments, key=lambda segment: sum(ch.isalpha() for ch in segment))
    if "*" in text:
        text = text.split("*")[-1]
    text = _VPA_RE.sub("", text)
    text = _REF_RE.sub(" ", text)
    text = _NOISE_WORDS.sub(" ", text)
    text = re.sub(r"[^A-Za-z0-9&.' ]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip(" .")
    if not text:
        return "Unknown"
    text = text.title()
    return re.sub(r"\bAtm\b", "ATM", text)


# --------------------------------------------------------- column mapping

_HEADER_HINTS = {
    "date": ("date",),
    "description": ("description", "narration", "details", "particulars", "remarks", "transaction"),
    "amount": ("amount", "value"),
    "debit": ("debit", "withdrawal", "withdraw", "paid out"),
    "credit": ("credit", "deposit", "paid in"),
    "direction": ("type", "dr/cr", "drcr", "cr/dr"),
}


@dataclass
class ColumnMapping:
    """Which column of a raw table holds what."""

    date: int
    description: int
    amount: int | None = None
    direction: int | None = None
    debit: int | None = None
    credit: int | None = None
    header_row: int | None = None


def _cell_kind(cell: str) -> str | None:
    lowered = cell.strip().lower()
    if not lowered:
        return None
    for kind, hints in _HEADER_HINTS.items():
        if any(hint in lowered for hint in hints):
            return kind
    return None


def _ratio(rows: Sequence[Sequence[str]], index: int, check: Callable[[Any], Any]) -> float:
    filled = checked = 0
    for row in rows:
        if index >= len(row):
            continue
        cell = row[index]
        if cell is None or not str(cell).strip():
            continue
        filled += 1
        if check(cell) is not None:
            checked += 1
    return checked / filled if filled else 0.0


def detect_columns(rows: Sequence[Sequence[str]]) -> ColumnMapping:
    """Locate the date/description/amount columns of a raw statement table.

    Works in two passes: header keywords first (when the table has a header
    row), then content-based heuristics for header-less or unusual layouts.
    """
    cleaned = [[("" if cell is None else str(cell)) for cell in row] for row in rows]
    if not any(any(cell.strip() for cell in row) for row in cleaned):
        raise ParseError("The statement contains no readable rows.")

    header_idx: int | None = None
    header_hits: dict[str, int] = {}
    for position, row in enumerate(cleaned[:10]):
        if not any(cell.strip() for cell in row):
            continue
        found: dict[str, int] = {}
        for column, cell in enumerate(row):
            kind = _cell_kind(cell)
            if kind and kind not in found:
                found[kind] = column
        core = {"date", "description", "amount", "debit", "credit"}
        if "date" in found and len(core & set(found)) >= 2:
            header_idx, header_hits = position, found
            break

    data_rows = cleaned[header_idx + 1 :] if header_idx is not None else cleaned
    data_rows = [row for row in data_rows if any(cell.strip() for cell in row)]
    if not data_rows:
        raise ParseError("Found a header but no transaction rows below it.")

    # Fast path: the header told us everything we need.
    if header_idx is not None:
        has_amount = "amount" in header_hits or "debit" in header_hits or "credit" in header_hits
        if "date" in header_hits and "description" in header_hits and has_amount:
            return ColumnMapping(
                date=header_hits["date"],
                description=header_hits["description"],
                amount=header_hits.get("amount"),
                debit=header_hits.get("debit"),
                credit=header_hits.get("credit"),
                direction=header_hits.get("direction"),
                header_row=header_idx,
            )

    # Content-based detection for header-less or unusual tables.
    width = max(len(row) for row in data_rows)
    if width < 2:
        raise ParseError("Could not find a table with enough columns to parse.")
    sample = data_rows[:400]

    date_scores = [_ratio(sample, index, parse_date) for index in range(width)]
    date_col = max(range(width), key=lambda index: date_scores[index])
    if date_scores[date_col] < 0.5:
        raise ParseError(
            "No column in this statement looks like a date column. "
            "If the format is unusual, run scripts/inspect_statement.py and open an issue."
        )

    amount_scores = [_ratio(sample, index, parse_amount) for index in range(width)]
    amount_candidates = [
        index for index in range(width) if index != date_col and amount_scores[index] >= 0.5
    ]
    if not amount_candidates:
        raise ParseError("No column in this statement looks like an amount column.")
    hinted_amount = header_hits.get("amount")
    if hinted_amount in amount_candidates:
        amount_col = hinted_amount
    else:
        amount_col = max(amount_candidates, key=lambda index: amount_scores[index])

    def textiness(index: int) -> float:
        lengths = [
            len(str(row[index]))
            for row in sample
            if index < len(row) and str(row[index]).strip() and parse_amount(row[index]) is None
        ]
        return sum(lengths) / len(lengths) if lengths else 0.0

    candidates = [index for index in range(width) if index not in (date_col, amount_col)]
    if not candidates:
        candidates = [date_col]  # degenerate single-column statement
    description_col = max(candidates, key=textiness)

    direction_col = None
    for index in candidates:
        if index != description_col and _ratio(sample, index, direction_from_text) >= 0.5:
            direction_col = index
            break

    return ColumnMapping(
        date=date_col,
        description=description_col,
        amount=amount_col,
        direction=direction_col,
        header_row=header_idx,
    )


# ----------------------------------------------------------- row assembly

_SUMMARY_ROW = re.compile(r"^\s*(total|sub\s*-?total|closing|opening|balance)\b", re.I)


def rows_to_transactions(
    rows: Sequence[Sequence[str]],
    mapping: ColumnMapping,
    source: str = "statement",
) -> pd.DataFrame:
    """Turn raw rows into a canonical transactions DataFrame."""
    records: list[dict[str, Any]] = []
    for row in rows:
        cells = [("" if cell is None else str(cell).strip()) for cell in row]
        if not any(cells):
            continue
        joined = " ".join(cells)
        if _SUMMARY_ROW.search(joined):
            continue
        if mapping.date >= len(cells):
            continue
        date_value = parse_date(cells[mapping.date])
        if date_value is None:
            continue

        amount: float | None = None
        direction: str | None = None
        raw_amount = ""

        if mapping.debit is not None or mapping.credit is not None:
            debit_value = (
                parse_amount(cells[mapping.debit])
                if mapping.debit is not None and mapping.debit < len(cells)
                else None
            )
            credit_value = (
                parse_amount(cells[mapping.credit])
                if mapping.credit is not None and mapping.credit < len(cells)
                else None
            )
            if debit_value is not None and debit_value != 0:
                amount, direction = abs(debit_value), "debit"
            elif credit_value is not None and credit_value != 0:
                amount, direction = abs(credit_value), "credit"
        else:
            raw_amount = (
                cells[mapping.amount]
                if mapping.amount is not None and mapping.amount < len(cells)
                else ""
            )
            parsed = parse_amount(raw_amount)
            if parsed is not None:
                amount = abs(parsed)
                if parsed < 0:
                    direction = "debit"

        if amount is None or amount <= 0:
            continue
        if direction is None and mapping.direction is not None and mapping.direction < len(cells):
            direction = direction_from_text(cells[mapping.direction])
        if direction is None:
            direction = direction_from_text(raw_amount)
        if direction is None:
            direction = "debit"  # conservative default; the UI can filter

        description = cells[mapping.description] if mapping.description < len(cells) else joined
        records.append(
            {
                "date": date_value,
                "description": description or joined,
                "amount": amount,
                "direction": direction,
                "source": source,
            }
        )

    if not records:
        raise ParseError(
            "Parsed the file, but no transaction rows were found. "
            "Make sure the export has date, description and amount columns."
        )
    return finalize_transactions(pd.DataFrame.from_records(records), source)
