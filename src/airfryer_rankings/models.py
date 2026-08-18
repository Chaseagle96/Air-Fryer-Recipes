from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from urllib.parse import urlsplit, urlunsplit

import yaml

UA = "AirFryerRankingsBot/4.0 (+https://github.com/Chaseagle96/Air-Fryer-Recipes; research crawler)"
HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}
KEY_RE = re.compile(r"(?:air[-_ ]?fry(?:er|ing|ed)|airfry(?:er|ing|ed))", re.I)
SPACE_RE = re.compile(r"[^a-z0-9]+")
NUMBER_RE = re.compile(r"-?\d[\d,]*(?:\.\d+)?")
MEASURE_RE = re.compile(
    r"\b(?:cups?|tablespoons?|tbsp|teaspoons?|tsp|ounces?|oz|pounds?|lbs?|grams?|g|kg|ml|milliliters?|liters?|l|pinch|dash|cloves?)\b",
    re.I,
)
GENERIC_TITLE_TOKENS = {
    "air", "fryer", "fried", "frying", "recipe", "recipes", "easy", "best", "crispy", "quick", "homemade",
}
DEFAULT_STATE = {
    "recipes": {},
    "url_catalog": {},
    "rank_history": [],
    "source_history": [],
    "anomaly_history": [],
    "migration": {},
    "schema_version": 4,
}
CATEGORY_RULES = {
    "Chicken": ("chicken", "wing", "wings", "drumstick", "drumsticks", "tender", "tenders"),
    "Potatoes": ("potato", "potatoes", "fries", "tater"),
    "Vegetables": (
        "broccoli", "cauliflower", "zucchini", "asparagus", "carrot", "carrots", "brussels", "sprout", "sprouts",
        "eggplant", "mushroom", "mushrooms", "green bean", "green beans", "vegetable", "vegetables", "squash",
    ),
    "Desserts": ("cake", "cookie", "cookies", "dessert", "donut", "doughnut", "apple", "brownie", "cinnamon", "churro"),
    "Beef": ("beef", "steak", "burger", "hamburger", "meatball", "meatballs"),
    "Pork": ("pork", "bacon", "sausage", "ham"),
    "Seafood": ("salmon", "shrimp", "fish", "cod", "tilapia", "tuna", "scallop", "scallops"),
    "Breakfast": ("breakfast", "egg", "eggs", "toast", "pancake", "waffle", "bacon", "hash brown", "hashbrown"),
    "Snacks": ("snack", "snacks", "chips", "fries", "nugget", "nuggets", "bite", "bites", "taquito", "taquitos"),
}


@dataclass
class RecipeRow:
    recipe_id: str
    title: str
    source: str
    url: str
    rating: float
    rating_count: int
    best_rating: float
    normalized_rating: float
    retrieved_at: str
    author: str = ""
    ingredient_signature: str = ""
    canonical_url: str = ""
    ingredients: tuple[str, ...] = ()
    instruction_signature: str = ""
    instruction_simhash: str = ""
    instructions: tuple[str, ...] = ()
    image_url: str = ""
    image_fingerprint: str = ""
    image_perceptual_hash: str = ""
    extraction_method: str = "jsonld"
    evidence_confidence: float = 0.65
    evidence_status: str = "schema_only"
    page_hash: str = ""
    etag: str = ""
    last_modified: str = ""
    schema_rating: float | None = None
    schema_rating_count: int | None = None
    visible_rating: float | None = None
    visible_rating_count: int | None = None
    rating_histogram: dict[str, int] = field(default_factory=dict)
    fetch_status: str = "fetched"
    categories: tuple[str, ...] = ()


@dataclass
class SourceConfig:
    domain: str
    enabled: bool = True
    max_urls: int = 250
    delay: float = 0.15
    sitemap_urls: tuple[str, ...] = ()
    discovery_urls: tuple[str, ...] = ()
    rating_selector: str = ""
    count_selector: str = ""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def normalize_text(value: str) -> str:
    return SPACE_RE.sub(" ", str(value).lower()).strip()


def normalize_ingredient(value: str) -> str:
    text = normalize_text(value)
    text = re.sub(r"\b\d+(?:\s+\d+\/\d+|\/\d+|\.\d+)?\b", " ", text)
    text = MEASURE_RE.sub(" ", text)
    return " ".join(text.split())


def ingredient_signature(ingredients: Iterable[str]) -> str:
    normalized = [normalize_text(x) for x in ingredients if normalize_text(x)]
    if not normalized:
        return ""
    payload = "\n".join(sorted(dict.fromkeys(normalized)))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def instruction_signature(instructions: Iterable[str]) -> str:
    normalized = [normalize_text(x) for x in instructions if normalize_text(x)]
    if not normalized:
        return ""
    payload = "\n".join(normalized)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def instruction_simhash(instructions: Iterable[str], bits: int = 64) -> str:
    tokens = []
    for instruction in instructions:
        tokens.extend(token for token in normalize_text(instruction).split() if len(token) > 2)
    if not tokens:
        return ""
    vector = [0] * bits
    for token in tokens:
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        value = int.from_bytes(digest[: bits // 8], "big")
        for bit in range(bits):
            vector[bit] += 1 if value & (1 << bit) else -1
    result = 0
    for bit, weight in enumerate(vector):
        if weight >= 0:
            result |= 1 << bit
    return f"{result:0{bits // 4}x}"


def fingerprint_image_url(value: str) -> str:
    if not value:
        return ""
    try:
        parts = urlsplit(value)
        normalized = urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path, "", ""))
    except Exception:
        normalized = value.strip().lower()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:20]


def categorize_recipe(title: str, ingredients: Iterable[str] = ()) -> tuple[str, ...]:
    haystack = normalize_text(title + " " + " ".join(str(x) for x in ingredients))
    categories = []
    for category, terms in CATEGORY_RULES.items():
        if any(term in haystack for term in terms):
            categories.append(category)
    return tuple(categories)


def load_sources(path: str | Path) -> list[SourceConfig]:
    data = yaml.safe_load(Path(path).read_text()) or {}
    defaults = data.get("defaults", {}) or {}
    out: list[SourceConfig] = []
    for item in data.get("sources", []):
        if not item.get("enabled", True):
            continue
        out.append(
            SourceConfig(
                domain=item["domain"].lower().strip(),
                enabled=True,
                max_urls=int(item.get("max_urls", defaults.get("max_urls", 250))),
                delay=float(item.get("delay", defaults.get("delay", 0.15))),
                sitemap_urls=tuple(item.get("sitemap_urls", []) or []),
                discovery_urls=tuple(item.get("discovery_urls", []) or []),
                rating_selector=str(item.get("rating_selector", "") or ""),
                count_selector=str(item.get("count_selector", "") or ""),
            )
        )
    return out
