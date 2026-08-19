from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

from ..model_config import ModelParameters
from ..models import parse_dt
from .normalization import category_baselines, expected_category_rating, recipe_categories, source_adjustments
from .priors import bayesian_posterior, global_prior, volume_prior_m
from .uncertainty import uncertainty_penalty


def fresh(item: dict, now: datetime, stale_days: int) -> bool:
    observed = parse_dt(item.get("last_seen_at") or item.get("retrieved_at"))
    return bool(observed and observed >= now - timedelta(days=stale_days))


def eligible_current(
    state: dict,
    stale_days: int,
    now: datetime | None = None,
    allowed_sources: set[str] | None = None,
) -> list[dict]:
    """Return only current, rankable recipes from the effective source set.

    ``allowed_sources`` is intentionally optional for the public library surface, but
    production orchestration passes the effective source domains loaded from the
    source registry. This makes a source suspension or block an immediate ranking
    eviction instead of waiting for the recipe's normal freshness window to expire.
    """

    now = now or datetime.now(timezone.utc)
    normalized_sources = None
    if allowed_sources is not None:
        normalized_sources = {str(source).lower().strip() for source in allowed_sources if str(source).strip()}
    return [
        dict(item)
        for item in state.get("recipes", {}).values()
        if fresh(item, now, stale_days)
        and (normalized_sources is None or str(item.get("source") or "").lower().strip() in normalized_sources)
        and int(item.get("rating_count", 0)) > 0
        and float(item.get("evidence_confidence", 0.60)) >= 0.60
        and item.get("evidence_status") != "conflict"
    ]


def score_current(
    current: list[dict],
    calibration: dict[str, dict] | None = None,
    params: ModelParameters | None = None,
) -> tuple[list[dict], dict]:
    params = params or ModelParameters()
    prior = global_prior(current)
    base_m, prior_strength = volume_prior_m(current, params)
    baselines = category_baselines(current, prior, params)
    adjustments = source_adjustments(current, prior, baselines, params)

    ranked: list[dict] = []
    for item in current:
        count = int(item["rating_count"])
        raw_rating = float(item["normalized_rating"])
        source_info = adjustments.get(item.get("source", ""), {"bias": 0.0})
        source_bias = float(source_info.get("bias", 0.0))
        adjusted_rating = max(0.0, min(5.0, raw_rating - source_bias))
        posterior = bayesian_posterior(adjusted_rating, count, prior, prior_strength)
        uncertainty, uncertainty_method = uncertainty_penalty(
            item,
            count,
            prior_strength,
            params.uncertainty_cap,
            calibration,
        )
        confidence = float(item.get("evidence_confidence", 0.60))
        evidence_penalty = max(0.0, params.evidence_confidence_target - confidence) * params.evidence_penalty_scale
        score = max(0.0, posterior - uncertainty - evidence_penalty)
        categories = recipe_categories(item)
        ranked.append(
            {
                "recipe_id": item["recipe_id"],
                "title": item["title"],
                "source": item.get("source", ""),
                "combined_sources": item.get("combined_sources", item.get("source", "")),
                "url": item.get("canonical_url") or item.get("url", ""),
                "rating": raw_rating,
                "rating_count": count,
                "source_bias": source_bias,
                "category_expected_rating": expected_category_rating(item, baselines, prior),
                "adjusted_rating": adjusted_rating,
                "posterior_mean": posterior,
                "uncertainty_penalty": uncertainty,
                "uncertainty_method": uncertainty_method,
                "evidence_penalty": evidence_penalty,
                "hierarchical_score": score,
                "evidence_confidence": confidence,
                "evidence_status": item.get("evidence_status", ""),
                "author": item.get("author", ""),
                "categories": " | ".join(categories),
                "duplicate_group_id": item.get("duplicate_group_id", ""),
                "duplicate_confidence": item.get("duplicate_confidence", 0.0),
                "last_seen_at": item.get("last_seen_at", ""),
                "_source_item": item,
            }
        )
    ranked.sort(key=lambda row: (row["hierarchical_score"], math.log1p(row["rating_count"])), reverse=True)
    for index, row in enumerate(ranked, 1):
        row["rank"] = index
    return ranked, {
        "global_prior": prior,
        "base_volume_prior_m": base_m,
        "volume_prior_m": prior_strength,
        "category_baselines": baselines,
        "source_adjustments": adjustments,
        "parameters": params.to_dict(),
    }
