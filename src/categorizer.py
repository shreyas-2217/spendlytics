"""Merchant categorisation: deterministic rules first, then cache, then LLM.

Design notes
------------
1. Rules cover Indian consumer merchants — including generic neighbourhood
   words (pharmacy, restaurant, supermarket, fuel point, tuition centre …) so
   that informal or unrecognised merchants still land in the right bucket.
2. Every LLM answer is cached on disk (``data/merchant_cache.json``), so the
   same merchant is never classified twice. Answers are validated against the
   fixed category list and normalised (casing, punctuation, fences).
3. Anything still unresolved falls back to heuristics — P2P markers, then
   person-name detection — and finally "Other". The app never crashes and
   never needs a key to produce a full report.
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
        # services of a parent brand must come before the parent itself,
        # and payment-relevant words before brand words
        (
            r"instamart|blinkit|zepto|bigbasket|jiomart|dmart|licious|reliance fresh"
            r"|more supermarket|more retail|spencers|kirana|super ?market|supermarket"
            r"|grocer(y|ies)|provision|general store|departmental store|mini ?mart"
            r"|vegetables|veggies|fresh fruits|fruit shop|dairy|aavin|amul|nandini"
            r"|milk ?(booth|parlour|parlor)|metro ?cash",
            "Groceries",
        ),
        (
            r"netflix|spotify|youtube ?premium|prime video|hotstar|jio ?cinema|disney|sonyliv|zee5"
            r"|icloud|google one|chatgpt|openai|claude|anthropic|adobe|canva|notion|github"
            r"|cult\.?fit|curefit|amazon prime|linkedin premium|membership|annual plan"
            r"|subscription",
            "Subscriptions",
        ),
        (
            r"swiggy|zomato|eatsure|faasos|domino|pizza hut|kfc|burger king|mcdonald|wendy|subway"
            r"|freshmenu|fresh ?menu|box8|behrouz|biryani ?blue|meghana|kritunga|kabab|kebab"
            r"|rolls?|wow ?momo|pizza|burger",
            "Food Delivery",
        ),
        (
            r"starbucks|third wave|blu[e]? tokai|chaayos|chai ?point|coffee|cafe|bakery|juice"
            r"|shake|dessert|ice ?cream|baskin|naturals|restaurant|restro|dhaba|kitchen"
            r"|eatery|tiffin|mess\b|canteen|sweets?|momo|cake|bhavan",
            "Eating Out",
        ),
        (
            r"uber|(?<![a-z])ola(?![a-z])|rapido|blusmart|namma ?metro|bmtc|yulu|bounce"
            r"|park ?\+|fastag|toll|(?<![a-z])cabs?(?![a-z])|taxi|rickshaw"
            r"|(?<![a-z])bus(?![a-z])|(?<![a-z])metro(?![a-z])|petrol|diesel|fuel"
            r"|filling station|iocl|bpcl|hpcl|indian oil|bharat petroleum|nayara|shell fuel"
            r"|garage|puncture|service station|ev ?charg|fleet ?x",
            "Transport",
        ),
        (
            r"jio(?! ?mart)|airtel|vodafone|(?<![a-z])vi(?![a-z])|act fibernet|fibernet|broadband"
            r"|bescom|bwssb|electricity|gas bill|indane|hp gas|lpg|water bill|tata power|recharge"
            r"|bsnl|hathway|tata ?sky|d2h|dish ?tv|sun ?direct|postpaid|bill ?desk"
            r"|adani electricity|mseb|kseb|tneb|bses|smart meter|cable ?tv"
            r"|(?<![a-z])cable(?![a-z])",
            "Utilities",
        ),
        (
            r"amazon|flipkart|myntra|ajio|meesho|nykaa|decathlon|croma|zudio|zara|h&m|uniqlo"
            r"|lenskart|titan|caratlane|reliance (digital|trends|smart)|vijay sales|pantaloons"
            r"|westside|max fashion|shoppers stop|bata|nike|adidas|puma|levis|allen solly"
            r"|van heusen|tanishq|kalyan jewell?ers|malabar gold|joyalukkas|first ?cry"
            r"|electro|electronics|appliances?|mobiles?|furniture|mattress|paints?\b"
            r"|hardware|garments?|textiles?|fashion|apparel|footwear|shoe"
            r"|salon|spa\b|barber|beauty|cosmetics?|grooming",
            "Shopping",
        ),
        (
            r"bookmyshow|pvr|inox|imax|cinema|steam|playstation|xbox|dream11|gaming|arcade"
            r"|amusement|water ?park|theme park|bowling|(?<![a-z])zoo(?![a-z])|museum",
            "Entertainment",
        ),
        (
            r"irctc|redbus|makemytrip|make ?my ?trip|goibibo|ixigo|indigo|air ?india|vistara"
            r"|spicejet|akasa|oyo|treebo|fabhotel|airbnb|hotel|resort|lodge|guest ?house"
            r"|home ?stay|(?<![a-z])inn(?![a-z])|travels?|tours?|yatra|cleartrip|railway"
            r"|(?<![a-z])flight",
            "Travel",
        ),
        (
            r"apollo|pharmeasy|netmeds|(?<![a-z])1mg|tata 1mg|medplus|practo|hospital|clinic"
            r"|dental|diagnostic|pharmacy|pharma|medicals?|medico|medicine|drug ?store"
            r"|nursing home|optical|ayurved|homeo|(?<![a-z])labs?(?![a-z])|gym|fitness|yoga",
            "Health",
        ),
        (
            r"udemy|coursera|guvi|scaler|unacademy|byju|christ university|christ college"
            r"|exam fee|tuition|college fee|school fee|stationery|book store|gangaram|blossom"
            r"|school|college|university|institute|academy|coaching|classes|admission"
            r"|library|physics ?wallah|vedantu|simplilearn|upgrad|edureka|nptel",
            "Education",
        ),
        (r"\batm\b|cash wdl|withdrawal|cash deposit", "Cash"),
        (
            r"charges|service charge|penalty|late fee|annual fee|convenience fee|sms charge"
            r"|minimum balance|\bgst\b|processing fee|\bemi\b|platform fee|gateway fee"
            r"|maintenance charge|\bamc\b",
            "Fees & Charges",
        ),
        (
            r"\brent\b|landlord|zolo|stanza|nestaway|paying guest|(?<![a-z])pg(?![a-z])"
            r"|hostel|house rent|room rent|flat rent|monthly rent",
            "Rent",
        ),
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
    "dmart": "DMart",
    "freshmenu": "FreshMenu",
    "uber": "Uber",
    "ola": "Ola",
    "rapido": "Rapido",
    "amazon": "Amazon",
    "amazon pay india": "Amazon",
    "flipkart": "Flipkart",
    "myntra": "Myntra",
    "netflix": "Netflix",
    "spotify": "Spotify",
    "icloud": "iCloud",
    "google one": "Google One",
    "jio": "Jio",
    "airtel": "Airtel",
    "bescom": "BESCOM",
    "bwssb": "BWSSB",
    "irctc": "IRCTC",
    "oyo": "OYO",
    "pvr": "PVR",
    "bookmyshow": "BookMyShow",
    "pharmeasy": "PharmEasy",
    "netmeds": "Netmeds",
    "tata 1mg": "Tata 1mg",
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

_CATEGORY_LOOKUP = {category.lower(): category for category in CATEGORIES}

#: Words that mark a merchant as a business even when the name looks personal.
_BUSINESS_WORDS = re.compile(
    r"(?i)\b(?:store|shop|traders?|enterprises?|agency|services?|solutions?|works|company"
    r"|co|pvt|ltd|llp|kart|mart|point|centre|center|hotel|restaurant|cafe|corner|house"
    r"|palace|plaza|kitchen|bakery|sweets|bhavan|dhaba|chicken|foods?|grill|tailors?"
    r"|boutique|parlour|parlor|garments|jewell?ers|opticals?|medicals?|pharmacy|provision"
    r"|showroom|studio|salon|spa|fitness)s?\b",
)


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


def _looks_like_person(merchant: str) -> bool:
    """Two to three plain alphabetic words with no business keywords — a person."""
    tokens = merchant.split()
    if not 1 < len(tokens) <= 3:
        return False
    if not all(token.isalpha() for token in tokens):
        return False
    return not _BUSINESS_WORDS.search(merchant)


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
            if _looks_like_p2p(str(frame["description"].iloc[position])) or _looks_like_person(
                merchant
            ):
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
        "You classify Indian UPI transaction merchants into exactly one spending "
        f"category. Allowed categories: {', '.join(CATEGORIES)}. "
        "Guidance for hard cases: person names or '@' handles with no business "
        "context are 'Transfers'; petrol pumps and cab services are 'Transport'; "
        "medical and pharmacy shops are 'Health'; tuition and coaching centres are "
        "'Education'; lpg/electricity/water/broadband payments are 'Utilities'; "
        "neighbourhood 'hotels' that are eateries are 'Eating Out'; jewellery, "
        "clothing and electronics shops are 'Shopping'; use 'Other' only as a last "
        "resort. Reply with ONLY a JSON object mapping each merchant to its "
        'category, for example {"blue tokai": "Eating Out"}. Never invent categories.'
    )
    mapping: dict[str, str] = {}
    for start in range(0, len(merchants), _LLM_BATCH):
        batch = merchants[start : start + _LLM_BATCH]
        prompt = "Merchants:\n" + "\n".join(f"- {merchant}" for merchant in batch)
        response = client.complete(system, prompt, json_mode=True, temperature=0)
        if not response:
            continue
        parsed = _extract_json_object(response)
        if not parsed:
            continue
        for merchant, category in parsed.items():
            normalized = _normalize_category(category)
            if normalized:
                mapping[str(merchant).strip().lower()] = normalized
    return mapping


def _normalize_category(value: object) -> str | None:
    """Map a model answer onto the allowed list, tolerating case/punctuation."""
    if not isinstance(value, str):
        return None
    key = value.strip().strip(".\"'`")
    key = " ".join(key.lower().replace("-", " ").replace("_", " ").split())
    return _CATEGORY_LOOKUP.get(key)


def _extract_json_object(text: str) -> dict | None:
    """Parse a JSON object, tolerating code fences or surrounding prose."""
    cleaned = _strip_fences(text)
    parsed = _try_parse_object(cleaned)
    if parsed is not None:
        return parsed
    match = re.search(r"\{.*\}", cleaned, re.S)
    if match:
        return _try_parse_object(match.group(0))
    return None


def _try_parse_object(text: str) -> dict | None:
    try:
        value = json.loads(text)
    except ValueError:
        return None
    return value if isinstance(value, dict) else None


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()
