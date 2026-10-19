"""Inspect an unfamiliar statement file — prints raw rows and what the parser sees.

Usage:
    python scripts/inspect_statement.py path/to/statement.pdf
    python scripts/inspect_statement.py path/to/statement.csv
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.parsers.base import ParseError, detect_columns  # noqa: E402


def _load_rows(path: Path) -> list[list[str]]:
    if path.suffix.lower() == ".pdf":
        import pdfplumber

        rows: list[list[str]] = []
        with pdfplumber.open(path) as pdf:
            for page_number, page in enumerate(pdf.pages, start=1):
                for table in page.extract_tables() or []:
                    for row in table:
                        cells = [("" if c is None else str(c).strip()) for c in row]
                        if any(cells):
                            rows.append(cells)
        return rows

    import csv
    import io

    text = path.read_text(encoding="utf-8", errors="replace")
    delimiter = ","
    try:
        delimiter = csv.Sniffer().sniff(text[:4096], delimiters=",;\t|").delimiter
    except csv.Error:
        pass
    return [row for row in csv.reader(io.StringIO(text), delimiter=delimiter) if any(row)]


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        raise SystemExit(1)
    path = Path(sys.argv[1])
    if not path.exists():
        print(f"File not found: {path}")
        raise SystemExit(1)

    rows = _load_rows(path)
    print(f"Read {len(rows)} raw rows from {path.name}\n")
    print("First 15 rows:")
    for row in rows[:15]:
        print("  | ".join(cell[:38] for cell in row))

    print()
    try:
        mapping = detect_columns(rows)
    except ParseError as exc:
        print(f"Column detection FAILED: {exc}")
        raise SystemExit(2)
    print("Detected column mapping:")
    print(f"  date        -> column {mapping.date}")
    print(f"  description -> column {mapping.description}")
    print(f"  amount      -> {mapping.amount}")
    print(f"  debit/credit-> {mapping.debit} / {mapping.credit}")
    print(f"  direction   -> {mapping.direction}")
    print(f"  header row  -> {mapping.header_row}")


if __name__ == "__main__":
    main()
