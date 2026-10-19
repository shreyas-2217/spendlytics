"""Parse CSV (and simple delimited text) bank exports."""

from __future__ import annotations

import csv
import io

import pandas as pd

from src.parsers.base import ParseError, detect_columns, rows_to_transactions


def parse_csv(file) -> tuple[pd.DataFrame, dict]:
    """Parse an uploaded CSV/TSV file (bytes, file-like, or path) into transactions."""
    if isinstance(file, (str, bytes)):
        raw: bytes | str = open(file, "rb").read() if isinstance(file, str) else file
    else:
        raw = file.read()

    if isinstance(raw, str):
        text: str | None = raw
    else:
        text = None
        for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
            try:
                text = raw.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
    if text is None:
        raise ParseError("Could not decode the file — is it really a CSV?")

    delimiter = ","
    try:
        delimiter = csv.Sniffer().sniff(text[:4096], delimiters=",;\t|").delimiter
    except csv.Error:
        pass

    rows = list(csv.reader(io.StringIO(text), delimiter=delimiter))
    mapping = detect_columns(rows)
    start = (mapping.header_row + 1) if mapping.header_row is not None else 0
    transactions = rows_to_transactions(rows[start:], mapping, source="csv")
    meta = {"rows_read": len(rows), "delimiter": delimiter, "warnings": []}
    return transactions, meta
