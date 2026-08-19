from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from . import source_expansion as _legacy
from . import source_registry as _registry

SOURCE_GATE_VERSION = 2

_v1_qualification_metrics = _legacy.qualification_metrics
_v1_hard_gate_failures = _legacy.hard_gate_failures
_v1_metrics_for_context = _legacy._metrics_for_context
_v1_load_contexts = _legacy._load_contexts


def qualification_metrics(
    pages: list[_legacy.SampledPage],
    *,
    candidate_url_count: int,
    robots_status: str,
    run_at: str,
    existing_recipes: list[dict[str, Any]],
) -> dict[str, Any]:
    """Separate rating availability from conditional extractor reliability."""

    metrics = _v1_qualification_metrics(
        pages,
        candidate_url_count=candidate_url_count,
        robots_status=robots_status,
        run_at=run_at,
        existing_recipes=existing_recipes,
    )
    recipe_pages = [page for page in pages if page.fetched and page.is_recipe]
    ranking_rows = [page for page in recipe_pages if page.ranking_extractable]
    evidence_pages = [page for page in recipe_pages if page.has_rating or page.ranking_extractable]

    metrics["ranking_evidence_pages"] = len(evidence_pages)
    metrics["ranking_evidence_coverage_ratio"] = (
        len(evidence_pages) / len(recipe_pages) if recipe_pages else 0.0
    )
    metrics["ranking_row_yield"] = len(ranking_rows) / len(recipe_pages) if recipe_pages else 0.0
    metrics["extraction_success_rate"] = (
        len(ranking_rows) / len(evidence_pages) if evidence_pages else None
    )
    return metrics


def score_source_quality(
    metrics: dict[str, Any], policy: dict[str, Any]
) -> tuple[float, dict[str, float]]:
    """Score publishers without requiring public star ratings for legitimacy."""

    weights = policy.get("weights", {}) or {}
    relevance = 100.0 * min(
        1.0,
        0.65 * float(metrics.get("vertical_relevance_ratio") or 0.0)
        + 0.35
        * min(
            1.0,
            float(metrics.get("qualifying_vertical_recipe_count") or 0)
            / max(1.0, float(policy.get("target_vertical_recipe_count") or 20)),
        ),
    )

    structure = float(metrics.get("recipe_structure_rate") or 0.0)
    completeness = float(metrics.get("field_completeness") or 0.0)
    substantive = float(metrics.get("substantive_recipe_ratio") or 0.0)
    conditional_extraction = metrics.get("extraction_success_rate")
    if conditional_extraction is None:
        extraction_unit = 0.50 * structure + 0.30 * completeness + 0.20 * substantive
    else:
        extraction_unit = (
            0.35 * structure
            + 0.25 * completeness
            + 0.20 * substantive
            + 0.20 * float(conditional_extraction)
        )
    extraction = 100.0 * min(1.0, extraction_unit)

    editorial = 100.0 * min(1.0, float(metrics.get("editorial_provenance_ratio") or 0.0))
    crawl = 100.0 * min(1.0, float(metrics.get("fetch_success_rate") or 0.0))
    rated = float(metrics.get("rating_coverage_ratio") or 0.0)
    conflicts = float(metrics.get("rating_conflict_ratio") or 0.0)
    rating_integrity = 70.0 if rated == 0 else max(0.0, 100.0 * (1.0 - conflicts))
    if bool(metrics.get("suspicious_uniform_rating_evidence")):
        rating_integrity = max(0.0, rating_integrity - 25.0)
    novelty = 100.0 * min(1.0, float(metrics.get("novelty_ratio") or 0.0))
    freshness = max(0.0, min(100.0, float(metrics.get("freshness_score") or 50.0)))
    general = 100.0 * max(
        0.0,
        min(
            1.0,
            0.55 * (1.0 - float(metrics.get("within_source_duplicate_ratio") or 0.0))
            + 0.30 * substantive
            + 0.15 * (1.0 - float(metrics.get("trap_url_ratio") or 0.0)),
        ),
    )
    components = {
        "vertical_relevance": relevance,
        "extraction_reliability": extraction,
        "editorial_provenance": editorial,
        "crawl_stability": crawl,
        "rating_integrity": rating_integrity,
        "unique_contribution": novelty,
        "freshness": freshness,
        "general_quality": general,
    }
    total_weight = sum(float(weights.get(name, 0.0)) for name in components)
    if total_weight <= 0:
        raise ValueError("source quality weights must sum to a positive value")
    score = sum(
        components[name] * float(weights.get(name, 0.0)) for name in components
    ) / total_weight
    return round(score, 3), {
        name: round(value, 3) for name, value in components.items()
    }


def hard_gate_failures(
    metrics: dict[str, Any], policy: dict[str, Any]
) -> tuple[list[str], list[str]]:
    permanent, temporary = _v1_hard_gate_failures(metrics, policy)
    hard = policy.get("hard_gates", {}) or {}
    evidence_pages = int(metrics.get("ranking_evidence_pages") or 0)
    min_evidence_pages = int(hard.get("min_ranking_evidence_pages_for_extraction_gate", 3))
    extraction_success = metrics.get("extraction_success_rate")
    if (
        evidence_pages >= min_evidence_pages
        and extraction_success is not None
        and float(extraction_success)
        < float(hard.get("min_extraction_success_rate", 0.60))
    ):
        permanent.append("ranking_extractor_incompatible")
    return list(dict.fromkeys(permanent)), list(dict.fromkeys(temporary))


def _metrics_for_context(
    context: _legacy.VerticalContext,
    evaluated: list[dict[str, Any]],
    run_at: str,
) -> dict[str, Any]:
    payload = _v1_metrics_for_context(context, evaluated, run_at)
    total_evidence = sum(int(row.get("ranking_evidence_pages") or 0) for row in evaluated)
    total_rows = sum(int(row.get("recipes_extracted") or 0) for row in evaluated)
    total_recognized = sum(int(row.get("recipes_recognized") or 0) for row in evaluated)
    payload["qualification_extraction_success_rate"] = (
        total_rows / total_evidence if total_evidence else None
    )
    payload["qualification_ranking_row_yield"] = (
        total_rows / total_recognized if total_recognized else 0.0
    )
    return payload


def _load_contexts(config: dict[str, Any]) -> list[_legacy.VerticalContext]:
    contexts = _v1_load_contexts(config)
    for context in contexts:
        context.registry["source_gate_version"] = SOURCE_GATE_VERSION
    return contexts


def install_gate_v2() -> None:
    """Install gate-v2 semantics into the shared source-expansion engine."""

    _registry.SOURCE_GATE_VERSION = SOURCE_GATE_VERSION
    _legacy.SOURCE_GATE_VERSION = SOURCE_GATE_VERSION
    _legacy.qualification_metrics = qualification_metrics
    _legacy.score_source_quality = score_source_quality
    _legacy.hard_gate_failures = hard_gate_failures
    _legacy._metrics_for_context = _metrics_for_context
    _legacy._load_contexts = _load_contexts


DiscoveryHit = _legacy.DiscoveryHit
SampledPage = _legacy.SampledPage
VerticalContext = _legacy.VerticalContext
build_query_family = _legacy.build_query_family


def load_source_discovery_config(path: str | Path) -> dict[str, Any]:
    install_gate_v2()
    return _legacy.load_source_discovery_config(path)


def run_source_expansion(
    config_path: str | Path,
    *,
    mode: str,
    seed_file: str | Path | None = None,
    dry_run: bool = False,
    run_at: str | None = None,
) -> dict[str, Any]:
    install_gate_v2()
    return _legacy.run_source_expansion(
        config_path,
        mode=mode,
        seed_file=seed_file,
        dry_run=dry_run,
        run_at=run_at,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Discover, qualify, and govern Recipe Intelligence source publishers (gate v2)"
    )
    parser.add_argument("--config", default="config/source_discovery.yaml")
    parser.add_argument("--mode", choices=("daily", "deep", "smoke"), default="daily")
    parser.add_argument("--seed-file", default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    result = run_source_expansion(
        Path(args.config),
        mode=args.mode,
        seed_file=args.seed_file,
        dry_run=args.dry_run,
    )
    print(json.dumps(result, indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
