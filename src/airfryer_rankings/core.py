"""Public compatibility surface for the Air Fryer Rankings engine.

Implementation is split across focused modules so crawling, evidence extraction,
storage, ranking, QA, calibration, and benchmarking can evolve independently
while existing imports remain stable.
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
    instruction_simhash,
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
from .storage import load_state, merge_observations, migrate_state, read_recent_records, save_state, write_run_records
from .ranking import bayesian_rank
from .dedupe import candidate_duplicate_pairs, dedupe_current, duplicate_similarity
from .qa import detect_anomalies, source_health_summary, source_reliability
from .calibration import build_empirical_uncertainty, build_historical_metrics, evidence_grade, volume_bucket
from .benchmarks import evaluate_dedupe_benchmark

__all__ = [
    "CATEGORY_RULES", "DEFAULT_STATE", "HEADERS", "KEY_RE", "UA",
    "RecipeRow", "SourceConfig", "bayesian_rank", "build_empirical_uncertainty",
    "build_historical_metrics", "candidate_duplicate_pairs", "categorize_recipe",
    "crawl_targets", "dedupe_current", "detect_anomalies", "discover_source_urls",
    "duplicate_similarity", "evaluate_dedupe_benchmark", "evidence_grade",
    "extract_recipe_from_html", "fingerprint_image_url", "get", "ingredient_signature",
    "instruction_signature", "instruction_simhash", "iter_sitemap_records", "jsonld_objects",
    "load_sources", "load_state", "make_session", "merge_observations", "migrate_state",
    "normalize_ingredient", "normalize_text", "now_iso", "parse_dt", "read_recent_records",
    "robots_and_sitemaps", "save_state", "select_refresh_targets", "source_health_summary",
    "source_reliability", "visible_rating_evidence", "volume_bucket", "write_run_records",
]
