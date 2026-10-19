"""Merchant categorisation: deterministic rules first, then cache, then LLM.

Design notes
------------
1. Rules cover the vast majority of Indian consumer merchants and cost nothing.
2. Every LLM answer is cached on disk (``data/merchant_cache.json``), so the
   same merchant is never classified twice.
3. Anything still unresolved falls back to heuristics (P2P detection) and
   finally "Other" — the app never crashes without an API key.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd

from src.llm import LLMClient
from src.parsers.base import clean_merchant

CATEGORIES = [
    "Food Delivery",
    "Groceries",
    "Eating Out",
    "Transport",
    "Shopping",
    "Subscriptions",
    "Rent",
    "Utilities",
    "Education",
    "Health",
    "Entertainment",
    "Travel",
    "Cash",
    "Transfers",
    "Fees & Charges",
    "Other",
]

#: (regex, category) — order matters: specific patterns come before generic ones.
RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(pattern, re.I), category)
    for pattern, category in [
        # services of a parent brand must come before the parent itself
        (
            r"instamart|blinkit|zepto|bigbasket|jiomart|dmart|licious|reliance fresh"
            r"|more supermarket|more retail|spencers|kirana",
            "Groceries",
        ),
        (
            r"netflix|spotify|youtube ?premium|prime video|hotstar|jio ?cinema|disney|sonyliv|zee5"
            r"|icloud|google one|chatgpt|openai|claude|anthropic|adobe|canva|notion|github"
            r"|cult\.?fit|curefit|amazon prime|linkedin premium",
            "Subscriptions",
        ),
        (
            r"swiggy|zomato|eatsure|faasos|domino|pizza hut|kfc|burger king|mcdonald|wendy|subway",
            "Food Delivery",
        ),
        (
            r"starbucks|third wave|blu[e]? tokai|chaayos|chai ?point|coffee|cafe|bakery|juice"
            r"|shake|dessert|ice cream|baskin|naturals",
            "Eating Out",
        ),
        (
            r"uber|(?<![a-z])ola(?![a-z])|rapido|blusmart|namma ?metro|bmtc|yulu|bounce"
            r"|park ?\+|fastag|toll",
            "Transport",
        ),
        (
            r"jio(?! ?mart)|airtel|vodafone|(?<![a-z])vi(?![a-z])|act fibernet|fibernet|broadband"
            r"|bescom|bwssb|electricity|gas bill|indane|hp gas|lpg|water bill|tata power|recharge",
            "Utilities",
        ),
        (
            r"amazon|flipkart|myntra|ajio|meesho|nykaa|decathlon|croma|zudio|zara|h&m|uniqlo"
            r"|lenskart|titan|caratlane",
            "Shopping",
        ),
        (r"bookmyshow|pvr|inox|imax|cinema|steam|playstation|xbox|dream11|gaming", "Entertainment"),
        (
            r"irctc|redbus|makemytrip|make ?my ?trip|goibibo|ixigo|indigo|air ?india|vistara"
            r"|spicejet|oyo|airbnb|hotel|resort",
            "Travel",
        ),
        (
            r"apollo|pharmeasy|netmeds|(?<![a-z])1mg|tata 1mg|medplus|practo|hospital|clinic"
            r"|dental|diagnostic",
            "Health",
        ),
        (
            r"udemy|coursera|guvi|scaler|unacademy|byju|christ university|christ college"
            r"|exam fee|tuition|college fee|stationery|book store|gangaram|blossom|school fee",
            "Education",
        ),
        (r"\batm\b|cash wdl|withdrawal|cash deposit", "Cash"),
        (
            r"charges|service charge|penalty|late fee|annual fee|convenience fee|sms charge"
            r"|minimum balance|\bgst\b|processing fee|emi",
            "Fees & Charges",
        ),
        (r"\brent\b|landlord|zolo|stanza|nestaway|paying guest", "Rent"),
    ]
]

_CACHE_PATH = Path(__file__).resolve().parent.parent / "data" / "merchant_cache.json"

_ALIASES = {
    "swiggy": "Swiggy",
    "swiggy instamart": "Swiggy Instamart",
    "zomato": "Zomato",
    "blinkit": "Blinkit",
    "zepto": "Zepto",
    "bigbasket": "BigBasket",
    "uber": "Uber",
    "ola": "Ola",
    "rapido": "Rapido",
    "amazon": "Amazon",
    "amazon pay india": "Amazon",
    "flipkart": "Flipkart",
    "myntra": "Myntra",
    "netflix": "Netflix",
    "spotify": "Spotify",
    "jio": "Jio",
    "airtel": "Airtel",
    "bescom": "BESCOM",
    "bwssb": "BWSSB",
    "atm cash wdl": "ATM Withdrawal",
    "atm withdrawal": "ATM Withdrawal",
    "landlord": "Landlord",
    "cult fit": "cult.fit",
    "cultfit": "cult.fit",
    "curefit": "cult.fit",
    "third wave coffee": "Third Wave Coffee",
    "blue tokai coffee": "Blue Tokai Coffee",
}

_LLM_BATCH = 40


def canonical_merchant(cleaned: str) -> str:
    """Map known labels to tidy display names."""
    key = cleaned.strip().lower()
    if key in _ALIASES:
        return _ALIASES[key]
    if len(cleaned) > 3 and cleaned.isupper():
        return cleaned.title()
    return cleaned


def match_category(*texts: str) -> str | None:
    """First rule that matches any of the given texts, else ``None``."""
    haystack = " ".join(texts).lower()
    for pattern, category in RULES:
        if pattern.search(haystack):
            return category
    return None


# ------------------------------------------------------------------ cache


def load_cache() -> dict[str, str]:
    """Merchant -> category map learned from previous LLM runs."""
    try:
        with open(_CACHE_PATH, encoding="utf-8") as handle:
            data = json.load(handle)
        return {str(key): str(value) for key, value in data.items()}
    except (OSError, ValueError):
        return {}


def save_cache(cache: dict[str, str]) -> None:
    """Persist the cache; failures are ignored (caching is best-effort)."""
    try:
        _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(_CACHE_PATH, "w", encoding="utf-8") as handle:
            json.dump(dict(sorted(cache.items())), handle, indent=1)
    except OSError:
        pass


# ------------------------------------------------------------ pipeline


def _looks_like_p2p(description: str) -> bool:
    return bool(re.search(r"\bp2a\b", description, re.I))


def categorize(
    df: pd.DataFrame,
    client: LLMClient | None = None,
    use_llm: bool = True,
) -> tuple[pd.DataFrame, dict]:
    """Assign a clean merchant + category to every row.

    Order: rules -> cache -> LLM (optional) -> fallback heuristics.
    Returns the enriched frame and a stats dict for the UI.
    """
    stats = {
        "total": len(df),
        "rules": 0,
        "cache": 0,
        "llm": 0,
        "fallback": 0,
        "other": 0,
        "llm_used": False,
        "unique_merchants": 0,
    }
    if df.empty:
        return df, stats

    frame = df.copy()
    frame["merchant"] = [canonical_merchant(clean_merchant(desc)) for desc in frame["description"]]

    client = client if (use_llm and client is not None and client.available()) else None
    stats["llm_used"] = client is not None
    stats["unique_merchants"] = frame["merchant"].nunique()

    cache = load_cache()
    categories: list[str] = []
    unresolved: dict[str, list[int]] = {}

    for position, (description, merchant) in enumerate(
        zip(frame["description"], frame["merchant"])
    ):
        category = match_category(description, merchant)
        if category is not None:
            stats["rules"] += 1
        else:
            cached = cache.get(merchant.lower())
            if cached in CATEGORIES:
                category = cached
                stats["cache"] += 1
            else:
                unresolved.setdefault(merchant, []).append(position)
                category = None
        categories.append(category or "")

    if unresolved and client is not None:
        mapping = _classify_with_llm(sorted(unresolved), client)
        if mapping:
            cache.update(mapping)
            save_cache(cache)
            for merchant, positions in list(unresolved.items()):
                category = mapping.get(merchant.lower())
                if category in CATEGORIES:
                    stats["llm"] += len(positions)
                    for position in positions:
                        categories[position] = category
                    unresolved.pop(merchant)

    for merchant, positions in unresolved.items():
        for position in positions:
            if _looks_like_p2p(str(frame["description"].iloc[position])):
                categories[position] = "Transfers"
                stats["fallback"] += 1
            else:
                categories[position] = "Other"
                stats["other"] += 1

    frame["category"] = categories
    return frame, stats


def _classify_with_llm(merchants: list[str], client: LLMClient) -> dict[str, str]:
    """Classify merchants in batches; returns a lower-cased key -> category map."""
    system = (
        "You classify Indian UPI transaction merchants into exactly one spending category. "
        f"Allowed categories: {', '.join(CATEGORIES)}. "
        "Reply with ONLY a JSON object mapping each input merchant to its category, "
        'for example {"blue tokai": "Eating Out"}. Never invent categories.'
    )
    mapping: dict[str, str] = {}
    for start in range(0, len(merchants), _LLM_BATCH):
        batch = merchants[start : start + _LLM_BATCH]
        prompt = "Merchants:\n" + "\n".join(f"- {merchant}" for merchant in batch)
        response = client.complete(system, prompt, json_mode=True, temperature=0)
        if not response:
            continue
        try:
            parsed = json.loads(_strip_fences(response))
        except ValueError:
            continue
        if not isinstance(parsed, dict):
            continue
        for merchant, category in parsed.items():
            if isinstance(category, str) and category in CATEGORIES:
                mapping[str(merchant).strip().lower()] = category
    return mapping


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()
