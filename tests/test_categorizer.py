"""Tests for merchant categorisation: rules, canonical names, cache, LLM fallback."""

import pandas as pd

from src import categorizer
from src.categorizer import canonical_merchant, categorize, match_category


def test_rules_hit_common_merchants():
    assert match_category("UPI/DR/1/RAZ*SWIGGY/swiggy@ybl", "Swiggy") == "Food Delivery"
    assert match_category("BLINKIT order", "Blinkit") == "Groceries"
    assert match_category("NETFLIX", "Netflix") == "Subscriptions"
    assert match_category("UBER", "Uber") == "Transport"
    assert match_category("BESCOM bill payment", "Bescom") == "Utilities"
    assert match_category("JIO RECHARGE", "Jio Recharge") == "Utilities"


def test_instamart_is_groceries_not_food_delivery():
    assert match_category("SWIGGY INSTAMART", "Swiggy Instamart") == "Groceries"


def test_canonical_alias():
    assert canonical_merchant("Atm Cash Wdl") == "ATM Withdrawal"
    assert canonical_merchant("Swiggy") == "Swiggy"


def _frame(descriptions: list[str]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": pd.date_range("2026-09-12", periods=len(descriptions)),
            "description": descriptions,
            "merchant": ["" for _ in descriptions],
            "amount": [100.0 for _ in descriptions],
            "direction": ["debit" for _ in descriptions],
            "category": ["" for _ in descriptions],
            "source": ["test" for _ in descriptions],
        }
    )


def test_categorize_without_llm(tmp_path, monkeypatch):
    monkeypatch.setattr(categorizer, "_CACHE_PATH", tmp_path / "cache.json")
    frame = _frame(
        [
            "UPI/DR/1/RAZ*SWIGGY/swiggy@ybl",
            "UPI/DR/2/NETFLIX/netflix@paytm",
            "UPI/P2A/3/Aarav Sharma/aarav@ybl",
        ]
    )
    out, stats = categorize(frame, client=None)
    assert list(out["category"]) == ["Food Delivery", "Subscriptions", "Transfers"]
    assert stats["rules"] == 2
    assert stats["fallback"] == 1
    assert stats["llm_used"] is False


class _FakeClient:
    def available(self):
        return True

    def complete(self, system, prompt, **kwargs):
        return '{"aarav sharma": "Transfers"}'


def test_categorize_with_llm_then_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(categorizer, "_CACHE_PATH", tmp_path / "cache.json")
    frame = _frame(["UPI/P2A/3/Aarav Sharma/aarav@ybl"])

    out, stats = categorize(frame, client=_FakeClient())
    assert out.iloc[0]["category"] == "Transfers"
    assert stats["llm"] == 1

    # Second run should be served entirely from the on-disk cache.
    out2, stats2 = categorize(frame, client=_FakeClient())
    assert out2.iloc[0]["category"] == "Transfers"
    assert stats2["cache"] == 1
    assert stats2["llm"] == 0


def test_generic_local_merchants_are_categorized():
    """Unbranded neighbourhood merchants should land in sensible buckets."""
    cases = [
        ("UPI/DR/1/SRI BALAJI MEDICALS/x@ybl", "Sri Balaji Medicals", "Health"),
        ("UPI/DR/2/ANNAPOORNA RESTAURANT/x@ybl", "Annapoorna Restaurant", "Eating Out"),
        ("UPI/DR/3/SHRI KRISHNA FUEL POINT/x@ybl", "Shri Krishna Fuel Point", "Transport"),
        ("UPI/DR/4/GREEN LEAF SUPERMARKET/x@ybl", "Green Leaf Supermarket", "Groceries"),
        ("UPI/DR/5/SUNRISE TUITION CENTRE/x@ybl", "Sunrise Tuition Centre", "Education"),
        ("UPI/DR/6/WOODLAND FURNITURE/x@ybl", "Woodland Furniture", "Shopping"),
        ("UPI/DR/7/GRAND PALACE HOTEL/x@ybl", "Grand Palace Hotel", "Travel"),
        ("UPI/DR/8/CITY CABLE TV/x@ybl", "City Cable Tv", "Utilities"),
    ]
    for description, merchant, expected in cases:
        assert match_category(description, merchant) == expected, merchant


def test_person_name_heuristic_and_trader_fallback(tmp_path, monkeypatch):
    monkeypatch.setattr(categorizer, "_CACHE_PATH", tmp_path / "cache.json")
    frame = _frame(
        [
            "UPI/P2A/1/Ravi Kumar/ravi@ybl",
            "UPI/DR/2/SHARP LINE TRADERS/x@ybl",
            "UPI/DR/3/BUNTY CHICKEN CORNER/x@ybl",
        ]
    )
    out, stats = categorize(frame, client=None)
    assert list(out["category"]) == ["Transfers", "Other", "Other"]
    assert stats["fallback"] == 1
    assert stats["other"] == 2


class _SloppyClient:
    """Returns fenced JSON, mixed casing, and one invalid category."""

    def available(self):
        return True

    def complete(self, system, prompt, **kwargs):
        return (
            "Sure! Here you go:\n"
            '```json\n{"weird emporium": "shopping", "bindu stores": "Nonsense"}\n```'
        )


def test_llm_answers_are_normalised_and_validated(tmp_path, monkeypatch):
    monkeypatch.setattr(categorizer, "_CACHE_PATH", tmp_path / "cache.json")
    frame = _frame(
        [
            "UPI/DR/1/WEIRD EMPORIUM/x@ybl",
            "UPI/DR/2/BINDU STORES/x@ybl",
            "UPI/DR/3/MEENA KUMARI/x@ybl",
        ]
    )
    out, stats = categorize(frame, client=_SloppyClient())
    categories = dict(zip(out["merchant"], out["category"]))
    assert categories["Weird Emporium"] == "Shopping"  # lower-case answer normalised
    assert categories["Bindu Stores"] == "Other"  # invalid category rejected
    assert categories["Meena Kumari"] == "Transfers"  # person-name fallback
    assert stats["llm"] == 1
    assert stats["other"] == 1
    assert stats["fallback"] == 1
