"""Deterministic synthetic statement used for demos and tests.

Regenerate the committed CSV with:

    python -m src.sample_data [output.csv]

The data is entirely fictional but shaped like a real Bengaluru student's
UPI life: recurring subscriptions, food delivery, transport, one shopping
spike (so the anomaly detector has something to find), P2P transfers and a
monthly allowance from home.
"""

from __future__ import annotations

import random
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

from src.models import finalize_transactions

SEED = 42
VPAS = ["ybl", "paytm", "okaxis", "okhdfcbank", "okicici", "axl"]


def _ref(rng: random.Random) -> str:
    return str(rng.randint(10**11, 10**12 - 1))


def _vpa(rng: random.Random, name: str) -> str:
    return f"{name}@{rng.choice(VPAS)}"


def _debit(rng: random.Random, label: str, slug: str) -> str:
    return f"UPI/DR/{_ref(rng)}/{label}/{_vpa(rng, slug)}"


def generate_sample_df(seed: int = SEED) -> pd.DataFrame:
    """Build ~6 months of realistic, deterministic transactions."""
    rng = random.Random(seed)
    rows: list[dict] = []

    def add(when: datetime, description: str, amount: float, direction: str = "debit") -> None:
        rows.append(
            {
                "date": when,
                "description": description,
                "amount": round(float(amount), 2),
                "direction": direction,
            }
        )

    months = [(2026, month) for month in range(5, 11)]  # May – October 2026
    cutoff = datetime(2026, 10, 18, 23, 59)

    def day(month: int, number: int, hour: int | None = None) -> datetime:
        return datetime(2026, month, number, hour if hour is not None else rng.randint(7, 22))

    def spread(month: int, labels: list[str], count: int, low: float, high: float) -> None:
        """Repeat a merchant label a few times in a month with random amounts."""
        for _ in range(count):
            label = rng.choice(labels)
            slug = label.split()[0].split("*")[-1].lower()
            add(
                day(month, rng.randint(1, 28)),
                _debit(rng, label, slug),
                rng.uniform(low, high),
            )

    for year, month in months:
        # --- recurring charges -------------------------------------------
        add(day(month, 1, 9), _debit(rng, "LANDLORD", "landlord"), 9500)          # rent
        add(day(month, 3, 10), _debit(rng, "JIO RECHARGE", "jio"), 239)          # mobile plan
        add(day(month, 5, 6), _debit(rng, "NETFLIX", "netflix"), 649)            # streaming
        add(day(month, 8, 8), _debit(rng, "SPOTIFY", "spotify"), 119)            # music
        add(day(month, 12, 7), _debit(rng, "CULTFIT", "curefit"), 999)           # gym
        add(day(month, 20, 7), _debit(rng, "ICLOUD", "icloud"), 75)              # storage

        # --- monthly allowance --------------------------------------------
        add(
            day(month, 1, 11),
            f"UPI/P2A/{_ref(rng)}/Dad/{_vpa(rng, 'dad')}",
            rng.randint(8000, 11000),
            "credit",
        )

        # --- lifestyle ------------------------------------------------------
        spread(
            month,
            ["RAZ*SWIGGY", "SWIGGY", "PAYTM*ZOMATO", "ZOMATO"],
            rng.randint(4, 7),
            160,
            620,
        )
        spread(month, ["BLINKIT", "ZEPTO", "DMART", "MORE RETAIL"], rng.randint(0, 3), 140, 900)
        spread(
            month,
            ["STARBUCKS", "THIRD WAVE COFFEE", "BLUE TOKAI COFFEE", "CHAAYOS"],
            rng.randint(0, 3),
            120,
            450,
        )
        spread(month, ["UBER", "OLA", "RAPIDO"], rng.randint(2, 5), 45, 320)
        spread(month, ["AMAZON", "FLIPKART", "MYNTRA", "AJIO"], rng.randint(0, 2), 200, 1500)

        if rng.random() < 0.5:
            add(
                day(month, rng.randint(1, 28)),
                _debit(rng, "APOLLO PHARMACY", "apollo"),
                rng.uniform(120, 480),
            )

        # cash withdrawals
        for _ in range(rng.randint(1, 2)):
            add(
                day(month, rng.randint(1, 28)),
                f"ATW-{_ref(rng)}/ATM CASH WDL/BENGALURU",
                rng.choice([500, 1000, 1500, 2000]),
            )

        # P2P to friends (bill splits)
        for _ in range(rng.randint(1, 3)):
            friend = rng.choice(["Aarav Sharma", "Diya Patel", "Rohan Iyer", "Sneha Rao"])
            add(
                day(month, rng.randint(1, 28)),
                f"UPI/P2A/{_ref(rng)}/{friend}/{_vpa(rng, 'friend')}",
                rng.uniform(50, 600),
            )

        # occasional refund credit
        if rng.random() < 0.35:
            add(
                day(month, rng.randint(1, 28)),
                f"UPI/CR/{_ref(rng)}/SWIGGY REFUND/{_vpa(rng, 'swiggy')}",
                rng.uniform(120, 400),
                "credit",
            )

    # --- planted stories -------------------------------------------------
    add(datetime(2026, 9, 14, 20), _debit(rng, "CROMA", "croma"), 8999)  # September spike
    add(datetime(2026, 9, 21, 19), _debit(rng, "MYNTRA", "myntra"), 2499)
    add(datetime(2026, 8, 9, 15), _debit(rng, "IRCTC", "irctc"), 1240)   # trip to Mysore
    add(datetime(2026, 8, 10, 11), _debit(rng, "OYO", "oyo"), 2100)
    add(datetime(2026, 7, 26, 18), _debit(rng, "BOOKMYSHOW", "bookmyshow"), 720)

    frame = pd.DataFrame.from_records(rows)
    frame = frame[frame["date"] <= cutoff]
    return finalize_transactions(frame, source="sample")


def main() -> None:
    output = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/sample_transactions.csv")
    frame = generate_sample_df()
    output.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output, index=False)
    print(f"Wrote {len(frame)} transactions to {output}")


if __name__ == "__main__":
    main()
