from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from .dedupe import dedupe_current
from .models import categorize_recipe, now_iso, parse_dt


MAX_SOURCE_BIAS = 0.15
EVIDENCE_CONFIDENCE_TARGET = 0.80
EVIDENCE_PENALTY_SCALE = 0.20


def _percentile(values: list[int], q: float) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    if len(values) == 1:
        return float(values[0])
    pos = (len(values) - 1) * q
    lo = math.floor(pos)
    hi = math.ceil(pos)
    if lo == hi:
        return float(values[lo])
    return values[lo] + (values[hi] - values[lo]) * (pos - lo)


def _fresh(recipe: dict, now: datetime, stale_days: int) -> bool:
    dt = parse_dt(recipe.get("last_seen_at") or recipe.get("retrieved_at"))
    return bool(dt and dt >= now - timedelta(days=stale_days))


def _source_adjustments(
    current: list[dict],
    global_prior: float,
    prior_strength: float = 20.0,
    max_abs_bias: float = MAX_SOURCE_BIAS,
) -> dict[str, dict]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for item in current:
        grouped[item.get("source", "")].append(item)
    result = {}
    for source, items in grouped.items():
        weights = [math.sqrt(max(1, int(x.get("rating_count", 1)))) for x in items]
        ratings = [float(x.get("normalized_rating", 0)) for x in items]
        raw_mean = sum(r * w for r, w in zip(ratings, weights)) / max(1e-9, sum(weights))
        n = float(len(items))
        shrunk_mean = (n / (n + prior_strength)) * raw_mean + (prior_strength / (n + prior_strength)) * global_prior
        raw_bias = shrunk_mean - global_prior
        bias = max(-max_abs_bias, min(max_abs_bias, raw_bias))
        result[source] = {
            "raw_mean": raw_mean,
            "shrunk_mean": shrunk_mean,
            "raw_bias": raw_bias,
            "bias": bias,
            "bias_capped": not math.isclose(raw_bias, bias, rel_tol=0.0, abs_tol=1e-12),
            "recipe_count": int(n),
        }
    return result


def bayesian_rank(state: dict, stale_days: int = 14, history_limit: int = 168) -> tuple[list[dict], dict]:
    now = datetime.now(timezone.utc)
    current = [
        dict(x)
        for x in state.get("recipes", {}).values()
        if _fresh(x, now, stale_days)
        and int(x.get("rating_count", 0)) > 0
        and float(x.get("evidence_confidence", 0.85)) >= 0.60
        and x.get("evidence_status") != "conflict"
    ]
    current, deduped, duplicate_rows = dedupe_current(current, detailed=True)
    if not current:
        return [], {
            "global_prior": 0.0,
            "volume_prior_m": 0.0,
            "candidate_count": 0,
            "deduplicated_count": deduped,
            "source_adjustments": {},
            "duplicate_groups": duplicate_rows,
        }

    counts = [int(x["rating_count"]) for x in current]
    weights = [math.sqrt(max(1, c)) for c in counts]
    ratings = [float(x["normalized_rating"]) for x in current]
    global_prior = sum(r * w for r, w in zip(ratings, weights)) / sum(weights)
    m = max(50.0, _percentile(counts, 0.60))
    source_adjustments = _source_adjustments(current, global_prior)

    previous_snapshot = state.get("rank_history", [])[-1] if state.get("rank_history") else None
    prev = {x["recipe_id"]: int(x["rank"]) for x in (previous_snapshot or {}).get("top200", (previous_snapshot or {}).get("top50", []))}

    ranked: list[dict] = []
    for item in current:
        v = int(item["rating_count"])
        raw_rating = float(item["normalized_rating"])
        source_info = source_adjustments.get(item.get("source", ""), {"bias": 0.0})
        source_bias = float(source_info.get("bias", 0.0))
        adjusted_rating = max(0.0, min(5.0, raw_rating - source_bias))
        posterior = (v / (v + m)) * adjusted_rating + (m / (v + m)) * global_prior
        histogram = item.get("rating_histogram") or {}
        if histogram:
            histogram_pairs = []
            for star, count in histogram.items():
                try:
                    histogram_pairs.append((float(star), int(count)))
                except Exception:
                    pass
            total_hist = sum(c for _, c in histogram_pairs)
            if total_hist > 1:
                hist_mean = sum(star * c for star, c in histogram_pairs) / total_hist
                hist_var = sum(((star - hist_mean) ** 2) * c for star, c in histogram_pairs) / max(1, total_hist - 1)
                uncertainty_penalty = min(0.25, 1.96 * math.sqrt(max(0.0, hist_var) / max(1.0, v + m)))
            else:
                uncertainty_penalty = min(0.25, 1.96 * 2.5 / math.sqrt(max(1.0, v + m)))
        else:
            uncertainty_penalty = min(0.25, 1.96 * 2.5 / math.sqrt(max(1.0, v + m)))
        confidence = float(item.get("evidence_confidence", 0.85))
        evidence_penalty = max(0.0, EVIDENCE_CONFIDENCE_TARGET - confidence) * EVIDENCE_PENALTY_SCALE
        hierarchical_score = max(0.0, posterior - uncertainty_penalty - evidence_penalty)
        previous_count = item.get("previous_rating_count")
        previous_seen = parse_dt(item.get("previous_seen_at"))
        current_seen = parse_dt(item.get("last_seen_at") or item.get("retrieved_at"))
        review_velocity_per_day = None
        if previous_count is not None and previous_seen and current_seen and current_seen > previous_seen:
            days = (current_seen - previous_seen).total_seconds() / 86400.0
            if days > 0:
                review_velocity_per_day = (v - int(previous_count)) / days
        categories = tuple(item.get("categories") or categorize_recipe(item.get("title", ""), item.get("ingredients", [])))
        ranked.append(
            {
                "recipe_id": item["recipe_id"],
                "title": item["title"],
                "source": item.get("source", ""),
                "combined_sources": item.get("combined_sources", item.get("source", "")),
                "url": item.get("canonical_url") or item.get("url", ""),
                "rating": raw_rating,
                "rating_count": v,
                "source_bias": source_bias,
                "adjusted_rating": adjusted_rating,
                "posterior_mean": posterior,
                "uncertainty_penalty": uncertainty_penalty,
                "evidence_penalty": evidence_penalty,
                "hierarchical_score": hierarchical_score,
                "evidence_confidence": confidence,
                "evidence_status": item.get("evidence_status", ""),
                "author": item.get("author", ""),
                "categories": " | ".join(categories),
                "duplicate_group_id": item.get("duplicate_group_id", ""),
                "duplicate_confidence": item.get("duplicate_confidence", 0.0),
                "last_seen_at": item.get("last_seen_at", ""),
                "rating_change": None if item.get("previous_rating") is None else raw_rating - float(item.get("previous_rating")),
                "review_count_change": None if item.get("previous_rating_count") is None else v - int(item.get("previous_rating_count")),
                "review_velocity_per_day": review_velocity_per_day,
            }
        )

    ranked.sort(key=lambda x: (x["hierarchical_score"], math.log1p(x["rating_count"])), reverse=True)
    for idx, row in enumerate(ranked, 1):
        row["rank"] = idx
        row["previous_rank"] = prev.get(row["recipe_id"])
        row["movement"] = prev[row["recipe_id"]] - idx if row["recipe_id"] in prev else None
        if row["recipe_id"] in state.get("recipes", {}):
            state["recipes"][row["recipe_id"]]["last_rank"] = idx

    run_at = now_iso()
    snapshot = {
        "run_at": run_at,
        "top200": [
            {
                "recipe_id": x["recipe_id"],
                "rank": x["rank"],
                "hierarchical_score": round(x["hierarchical_score"], 8),
                "rating": x["rating"],
                "rating_count": x["rating_count"],
            }
            for x in ranked[:200]
        ],
    }
    history = state.setdefault("rank_history", [])
    history.append(snapshot)
    if len(history) > history_limit:
        del history[:-history_limit]

    return ranked, {
        "global_prior": global_prior,
        "volume_prior_m": m,
        "candidate_count": len(current),
        "deduplicated_count": deduped,
        "stale_days": stale_days,
        "history_snapshots": len(history),
        "source_adjustments": source_adjustments,
        "duplicate_groups": duplicate_rows,
        "max_source_bias": MAX_SOURCE_BIAS,
        "formula": "hierarchical_score = BayesianPosterior(capped source-adjusted rating) - uncertainty penalty - evidence penalty",
    }
