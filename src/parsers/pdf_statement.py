"""Parse PDF statement exports (Google Pay, PhonePe, bank e-statements).

Uses pdfplumber to extract tables from every page, then falls back to
content-based column detection so many different layouts are supported.
"""

from __future__ import annotations

import re

import pandas as pd

from src.parsers.base import ParseError, detect_columns, rows_to_transactions

_WHITESPACE = re.compile(r"\s+")


def _detect_source(text: str) -> str:
    lowered = text.lower()
    if "google pay" in lowered or "google india digital" in lowered:
        return "gpay"
    if "phonepe" in lowered:
        return "phonepe"
    if "paytm" in lowered:
        return "paytm"
    return "pdf-statement"


def parse_pdf(file) -> tuple[pd.DataFrame, dict]:
    """Extract tables from a statement PDF and turn them into transactions."""
    import pdfplumber  # imported lazily so CSV-only setups work without it

    rows: list[list[str]] = []
    first_page_text = ""
    with pdfplumber.open(file) as pdf:
        page_count = len(pdf.pages)
        if page_count:
            first_page_text = (pdf.pages[0].extract_text() or "")[:5000]
        for page in pdf.pages:
            for table in page.extract_tables() or []:
                for row in table:
                    cells = [
                        _WHITESPACE.sub(" ", str(cell)).strip() if cell is not None else ""
                        for cell in row
                    ]
                    if any(cells):
                        rows.append(cells)

    if not rows:
        raise ParseError(
            "No table found in this PDF. Make sure it's the text-based statement export "
            "(Google Pay → Get statement, PhonePe → Account statement), not a screenshot."
        )

    mapping = detect_columns(rows)
    start = (mapping.header_row + 1) if mapping.header_row is not None else 0
    source = _detect_source(first_page_text)
    transactions = rows_to_transactions(rows[start:], mapping, source=source)
    meta = {"pages": page_count, "raw_rows": len(rows), "warnings": []}
    return transactions, meta
