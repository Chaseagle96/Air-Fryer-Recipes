"""Public compatibility surface for the Air Fryer Rankings engine.

Implementation is split across focused modules so crawling, evidence extraction,
storage, ranking, QA, calibration, backtesting, contracts, and benchmarking can
evolve independently while existing imports remain stable.
"""

from collections.abc import Iterable

from .archive import history_storage_health, load_storage_policy, write_history_parquet
from .backtesting import history_span_days, run_historical_backtest
from .benchmarks import build_dedupe_label_queue, evaluate_dedupe_benchmark
from .calibration import build_empirical_uncertainty, build_historical_metrics, evidence_grade, volume_bucket
from .contracts import contract_manifest, write_contract_manifest
from .crawler import crawl_targets
from .crawler import select_refresh_targets as _select_refresh_targets
from .dedupe import candidate_duplicate_pairs, dedupe_current, duplicate_similarity
from .discovery import discover_source_urls
from .evidence import jsonld_objects, visible_rating_evidence
from .evidence_calibration import apply_evidence_calibration, evaluate_evidence_labels
from .extract import extract_recipe_from_html
from .http import get, iter_sitemap_records, make_session, robots_and_sitemaps
from .model_config import DEFAULT_MODEL_PARAMETERS, ModelParameters, load_model_config
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
from .observability import build_pipeline_metrics
from .qa import detect_anomalies, source_health_summary, source_reliability, temporal_anomalies
from .quality_gate import assert_publishable, evaluate_publish_gate, load_previous_serving_snapshot, write_quality_gate
from .ranking import bayesian_rank
from .ranking_components import bayesian_posterior, robustness_lab, score_current, uncertainty_penalty
from .schemas import validate_observation_record, validate_ranked_recipe, validate_records, validate_source_health
from .storage import load_state, merge_observations, migrate_state, read_recent_records, save_state, write_run_records
from .structure import dom_structure_fingerprint, rating_evidence_signature, schema_signature, structure_metadata


def select_refresh_targets(
    state: dict,
    sources: Iterable[SourceConfig],
    mode: str,
    global_max_urls: int | None = None,
    hourly_limit: int = 100,
) -> list[dict]:
    """Select crawl targets and persist the exact effective source scope for ranking."""

    source_list = list(sources)
    state["effective_source_domains"] = sorted({source.domain for source in source_list})
    return _select_refresh_targets(
        state,
        source_list,
        mode,
        global_max_urls=global_max_urls,
        hourly_limit=hourly_limit,
    )


__all__ = [
    "CATEGORY_RULES",
    "DEFAULT_MODEL_PARAMETERS",
    "DEFAULT_STATE",
    "HEADERS",
    "KEY_RE",
    "UA",
    "ModelParameters",
    "RecipeRow",
    "SourceConfig",
    "apply_evidence_calibration",
    "assert_publishable",
    "bayesian_posterior",
    "bayesian_rank",
    "build_dedupe_label_queue",
    "build_empirical_uncertainty",
    "build_historical_metrics",
    "build_pipeline_metrics",
    "candidate_duplicate_pairs",
    "categorize_recipe",
    "contract_manifest",
    "crawl_targets",
    "dedupe_current",
    "detect_anomalies",
    "discover_source_urls",
    "dom_structure_fingerprint",
    "duplicate_similarity",
    "evaluate_dedupe_benchmark",
    "evaluate_evidence_labels",
    "evaluate_publish_gate",
    "evidence_grade",
    "extract_recipe_from_html",
    "fingerprint_image_url",
    "get",
    "history_span_days",
    "history_storage_health",
    "ingredient_signature",
    "instruction_signature",
    "instruction_simhash",
    "iter_sitemap_records",
    "jsonld_objects",
    "load_model_config",
    "load_previous_serving_snapshot",
    "load_sources",
    "load_state",
    "load_storage_policy",
    "make_session",
    "merge_observations",
    "migrate_state",
    "normalize_ingredient",
    "normalize_text",
    "now_iso",
    "parse_dt",
    "rating_evidence_signature",
    "read_recent_records",
    "robots_and_sitemaps",
    "robustness_lab",
    "run_historical_backtest",
    "save_state",
    "schema_signature",
    "score_current",
    "select_refresh_targets",
    "source_health_summary",
    "source_reliability",
    "structure_metadata",
    "temporal_anomalies",
    "uncertainty_penalty",
    "validate_observation_record",
    "validate_ranked_recipe",
    "validate_records",
    "validate_source_health",
    "visible_rating_evidence",
    "volume_bucket",
    "write_contract_manifest",
    "write_history_parquet",
    "write_quality_gate",
    "write_run_records",
]
