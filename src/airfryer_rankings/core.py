"""Public compatibility surface for the Air Fryer Rankings engine.

Implementation is split across focused modules so crawling, evidence extraction,
storage, ranking, and QA can evolve independently while existing imports remain
stable.
"""

from .models import (
    CATEGORY_RULES,
    DEFAULT_STATE,
    HEADERS,
    KEY_RE,
    UA,
    RecipeRow,
    SourceConfig,
    categorize_recipe,
    fingerprint_image_url,
    ingredient_signature,
    instruction_signature,
    load_sources,
    normalize_ingredient,
    normalize_text,
    now_iso,
    parse_dt,
)
from .extract import extract_recipe_from_html
from .evidence import jsonld_objects, visible_rating_evidence
from .http import get, iter_sitemap_records, make_session, robots_and_sitemaps
from .crawler import crawl_targets, select_refresh_targets
from .discovery import discover_source_urls
from .storage import load_state, merge_observations, read_recent_records, save_state, write_run_records
from .ranking import bayesian_rank
from .dedupe import dedupe_current, duplicate_similarity
from .qa import detect_anomalies, source_reliability

__all__ = [
    "CATEGORY_RULES", "DEFAULT_STATE", "HEADERS", "KEY_RE", "UA",
    "RecipeRow", "SourceConfig", "bayesian_rank", "categorize_recipe",
    "crawl_targets", "dedupe_current", "detect_anomalies", "discover_source_urls",
    "duplicate_similarity", "extract_recipe_from_html", "fingerprint_image_url",
    "get", "ingredient_signature", "instruction_signature", "iter_sitemap_records",
    "jsonld_objects", "load_sources", "load_state", "make_session",
    "merge_observations", "normalize_ingredient", "normalize_text", "now_iso",
    "parse_dt", "read_recent_records", "robots_and_sitemaps", "save_state",
    "select_refresh_targets", "source_reliability", "visible_rating_evidence",
    "write_run_records",
]
