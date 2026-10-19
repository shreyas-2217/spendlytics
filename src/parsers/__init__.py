"""Statement parsers: pick the right one for an uploaded file."""

from __future__ import annotations

import pandas as pd

from src.parsers.base import ParseError
from src.parsers.csv_statement import parse_csv
from src.parsers.pdf_statement import parse_pdf

__all__ = ["ParseError", "parse_statement"]


def parse_statement(file, filename: str) -> tuple[pd.DataFrame, dict]:
    """Parse *file* based on its filename extension, with content sniffing."""
    name = (filename or "").lower()
    if name.endswith(".pdf"):
        return parse_pdf(file)
    if name.endswith((".csv", ".txt", ".tsv")):
        return parse_csv(file)

    # Unknown extension: sniff the leading bytes for a PDF signature.
    head = b""
    if hasattr(file, "read"):
        head = file.read(5) or b""
        file.seek(0)
    if head.startswith(b"%PDF"):
        return parse_pdf(file)
    return parse_csv(file)
