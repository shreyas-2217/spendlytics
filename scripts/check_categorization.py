"""Smoke-test the LLM categorisation path on unrecognised merchants.

Usage:
    python scripts/check_categorization.py

Runs a handful of deliberately obscure merchants (no brand names, no
rule keywords) through the real categoriser with the configured key and
prints the category each one received plus where it came from.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402

from src.categorizer import categorize  # noqa: E402
from src.llm import LLMClient  # noqa: E402

MERCHANTS = [
    "BUNTY CHICKEN CORNER",
    "LAKSHMI NARAYANAN",
    "TIME SQUARE WATCH SHOWROOM",
    "FAST TRACK CAR CARE CENTRE",
    "GREEN BASKET ORGANIC FARM",
    "UNICORN VENTURES LLP",
]


def main() -> int:
    client = LLMClient()
    print(f"Provider: {client.provider if client.available() else 'none (no key)'}")
    if not client.available():
        print("No key configured — the rules/cache/heuristics path still works.")
        return 0

    frame = pd.DataFrame(
        {
            "date": pd.date_range("2026-09-01", periods=len(MERCHANTS)),
            "description": [
                f"UPI/DR/45{index:06d}/{name}/x@ybl" for index, name in enumerate(MERCHANTS)
            ],
            "amount": [499.0] * len(MERCHANTS),
            "direction": ["debit"] * len(MERCHANTS),
            "source": ["check"] * len(MERCHANTS),
        }
    )

    out, stats = categorize(frame, client)
    print()
    for _, row in out.iterrows():
        print(f"  {str(row['merchant']):38s} -> {row['category']}")
    print()
    print(
        f"rules={stats['rules']} cache={stats['cache']} llm={stats['llm']} "
        f"person-to-person={stats['fallback']} unlisted={stats['other']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
