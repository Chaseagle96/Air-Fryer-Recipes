from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from statistics import mean, pstdev

from .calibration import empirical_penalty, evidence_grade
from .dedupe import dedupe_current
from .models import categorize_recipe, now_iso, parse_dt

MAX_SOURCE_BIAS = 0.15
EVIDENCE_CONFIDENCE_TARGET = 0.80
EVIDENCE_PENALTY_SCALE = 0.20
DEFAULT_UNCERTAINTY_CAP = 0.25
SOURCE_PRIOR_STRENGTH = 20.0
CATEGORY_PRIOR_STRENGTH = 20.0


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


def _eligible_current(state: dict, stale_days: int) -> list[dict]:
    now = datetime.now(timezone.utc)
    return [
        dict(x)
        for x in state.get("recipes", {}).values()
        if _fresh(x, now, stale_days)
        and int(x.get("rating_count", 0)) > 0
        and float(x.get("evidence_confidence", 0.60)) >= 0.60
        and x.get("evidence_status") != "conflict"
    ]


def _recipe_categories(item: dict) -> tuple[str, ...]:
    raw = item.get("categories")
    if isinstance(raw, str):
        values = tuple(x.strip() for x in raw.split("|") if x.strip())
        if values:
            return values
    if raw:
        return tuple(raw)
    return tuple(categorize_recipe(item.get("title", ""), item.get("ingredients", [])))


def _category_baselines(current: list[dict], global_prior: float, prior_strength: float = CATEGORY_PRIOR_STRENGTH) -> dict[str, dict]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for item in current:
        for category in _recipe_categories(item):
            grouped[category].append(item)
    result: dict[str, dict] = {}
    for category, items in grouped.items():
        weights = [math.sqrt(max(1, int(x.get("rating_count", 1)))) for x in items]
        ratings = [float(x.get("normalized_rating", 0)) for x in items]
        raw_mean = sum(r * w for r, w in zip(ratings, weights)) / max(1e-9, sum(weights))
        n = float(len(items))
        shrunk = (n / (n + prior_strength)) * raw_mean + (prior_strength / (n + prior_strength)) * global_prior
        result[category] = {"raw_mean": raw_mean, "shrunk_mean": shrunk, "recipe_count": int(n)}
    return result


def _expected_category_rating(item: dict, baselines: dict[str, dict], global_prior: float) -> float:
    values = [float(baselines[x]["shrunk_mean"]) for x in _recipe_categories(item) if x in baselines]
    return sum(values) / len(values) if values else global_prior


def _source_adjustments(
    current: list[dict],
    global_prior: float,
    category_baselines: dict[str, dict],
    prior_strength: float = SOURCE_PRIOR_STRENGTH,
    max_abs_bias: float = MAX_SOURCE_BIAS,
) -> dict[str, dict]:
    grouped: dict[str, list[tuple[dict, float]]] = defaultdict(list)
    for item in current:
        expected = _expected_category_rating(item, category_baselines, global_prior)
        grouped[item.get("source", "")].append((item, expected))
    result = {}
    for source, pairs in grouped.items():
        weights = [math.sqrt(max(1, int(item.get("rating_count", 1)))) for item, _ in pairs]
        ratings = [float(item.get("normalized_rating", 0)) for item, _ in pairs]
        residuals = [rating - expected for rating, (_, expected) in zip(ratings, pairs)]
        raw_mean = sum(r * w for r, w in zip(ratings, weights)) / max(1e-9, sum(weights))
        raw_residual = sum(r * w for r, w in zip(residuals, weights)) / max(1e-9, sum(weights))
        n = float(len(pairs))
        shrunk_residual = (n / (n + prior_strength)) * raw_residual
        bias = max(-max_abs_bias, min(max_abs_bias, shrunk_residual))
        result[source] = {
            "raw_mean": raw_mean,
            "raw_category_adjusted_bias": raw_residual,
            "shrunk_category_adjusted_bias": shrunk_residual,
            "bias": bias,
            "bias_capped": not math.isclose(shrunk_residual, bias, rel_tol=0.0, abs_tol=1e-12),
            "recipe_count": int(n),
        }
    return result


def _histogram_penalty(histogram: dict, v: int, m: float, cap: float) -> float | None:
    pairs = []
    for star, count in (histogram or {}).items():
        try:
            pairs.append((float(star), int(count)))
        except Exception:
            pass
    total = sum(c for _, c in pairs)
    if total <= 1:
        return None
    hist_mean = sum(star * c for star, c in pairs) / total
    hist_var = sum(((star - hist_mean) ** 2) * c for star, c in pairs) / max(1, total - 1)
    return min(cap, 1.96 * math.sqrt(max(0.0, hist_var) / max(1.0, v + m)))


def _uncertainty_penalty(item: dict, v: int, m: float, cap: float, calibration: dict[str, dict] | None) -> tuple[float, str]:
    histogram_value = _histogram_penalty(item.get("rating_histogram") or {}, v, m, cap)
    if histogram_value is not None:
        return histogram_value, "rating_histogram"
    empirical_value, method = empirical_penalty(calibration, v)
    if empirical_value is not None:
        return min(cap, empirical_value), method
    return min(cap, 1.96 * 2.5 / math.sqrt(max(1.0, v + m))), "theoretical_max_variance"


def _score_current(
    current: list[dict],
    calibration: dict[str, dict] | None = None,
    *,
    max_source_bias: float = MAX_SOURCE_BIAS,
    evidence_penalty_scale: float = EVIDENCE_PENALTY_SCALE,
    m_multiplier: float = 1.0,
    uncertainty_cap: float = DEFAULT_UNCERTAINTY_CAP,
    source_prior_strength: float = SOURCE_PRIOR_STRENGTH,
) -> tuple[list[dict], dict]:
    counts = [int(x["rating_count"]) for x in current]
    weights = [math.sqrt(max(1, c)) for c in counts]
    ratings = [float(x["normalized_rating"]) for x in current]
    global_prior = sum(r * w for r, w in zip(ratings, weights)) / sum(weights)
    base_m = max(50.0, _percentile(counts, 0.60))
    m = max(1.0, base_m * m_multiplier)
    category_baselines = _category_baselines(current, global_prior)
    source_adjustments = _source_adjustments(
        current,
        global_prior,
        category_baselines,
        prior_strength=source_prior_strength,
        max_abs_bias=max_source_bias,
    )

    ranked: list[dict] = []
    for item in current:
        v = int(item["rating_count"])
        raw_rating = float(item["normalized_rating"])
        source_info = source_adjustments.get(item.get("source", ""), {"bias": 0.0})
        source_bias = float(source_info.get("bias", 0.0))
        adjusted_rating = max(0.0, min(5.0, raw_rating - source_bias))
        posterior = (v / (v + m)) * adjusted_rating + (m / (v + m)) * global_prior
        uncertainty_penalty, uncertainty_method = _uncertainty_penalty(item, v, m, uncertainty_cap, calibration)
        confidence = float(item.get("evidence_confidence", 0.60))
        evidence_penalty = max(0.0, EVIDENCE_CONFIDENCE_TARGET - confidence) * evidence_penalty_scale
        hierarchical_score = max(0.0, posterior - uncertainty_penalty - evidence_penalty)
        categories = _recipe_categories(item)
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
                "category_expected_rating": _expected_category_rating(item, category_baselines, global_prior),
                "adjusted_rating": adjusted_rating,
                "posterior_mean": posterior,
                "uncertainty_penalty": uncertainty_penalty,
                "uncertainty_method": uncertainty_method,
                "evidence_penalty": evidence_penalty,
                "hierarchical_score": hierarchical_score,
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
    ranked.sort(key=lambda x: (x["hierarchical_score"], math.log1p(x["rating_count"])), reverse=True)
    for idx, row in enumerate(ranked, 1):
        row["rank"] = idx
    return ranked, {
        "global_prior": global_prior,
        "base_volume_prior_m": base_m,
        "volume_prior_m": m,
        "category_baselines": category_baselines,
        "source_adjustments": source_adjustments,
    }


def _spearman(base: dict[str, int], other: dict[str, int], ids: list[str]) -> float | None:
    pairs = [(base[x], other[x]) for x in ids if x in base and x in other]
    if len(pairs) < 2:
        return None
    xs = [x for x, _ in pairs]
    ys = [y for _, y in pairs]
    mx, my = mean(xs), mean(ys)
    numerator = sum((x - mx) * (y - my) for x, y in pairs)
    denom = math.sqrt(sum((x - mx) ** 2 for x in xs) * sum((y - my) ** 2 for y in ys))
    return numerator / denom if denom else 1.0


def _kendall(base: dict[str, int], other: dict[str, int], ids: list[str]) -> float | None:
    ids = [x for x in ids if x in base and x in other]
    if len(ids) < 2:
        return None
    concordant = 0
    discordant = 0
    for i, left in enumerate(ids):
        for right in ids[i + 1:]:
            product = (base[left] - base[right]) * (other[left] - other[right])
            if product > 0:
                concordant += 1
            elif product < 0:
                discordant += 1
    total = concordant + discordant
    return (concordant - discordant) / total if total else 1.0


def _robustness(current: list[dict], baseline: list[dict], calibration: dict[str, dict] | None) -> tuple[dict[str, dict], dict]:
    base_positions = {row["recipe_id"]: row["rank"] for row in baseline}
    positions: dict[str, list[int]] = defaultdict(list)
    top10_hits: dict[str, int] = defaultdict(int)
    top50_hits: dict[str, int] = defaultdict(int)
    simulation_metrics = []
    simulations = 0

    for max_bias in (0.10, 0.15, 0.20):
        for evidence_scale in (0.10, 0.20, 0.30):
            for m_multiplier in (0.80, 1.20):
                for uncertainty_cap in (0.20, 0.30):
                    sim, _ = _score_current(
                        current,
                        calibration,
                        max_source_bias=max_bias,
                        evidence_penalty_scale=evidence_scale,
                        m_multiplier=m_multiplier,
                        uncertainty_cap=uncertainty_cap,
                    )
                    simulations += 1
                    sim_positions = {row["recipe_id"]: row["rank"] for row in sim}
                    for rid, rank in sim_positions.items():
                        positions[rid].append(rank)
                        if rank <= 10:
                            top10_hits[rid] += 1
                        if rank <= 50:
                            top50_hits[rid] += 1
                    top200_ids = [row["recipe_id"] for row in baseline[:200]]
                    top100_ids = [row["recipe_id"] for row in baseline[:100]]
                    simulation_metrics.append(
                        {
                            "max_source_bias": max_bias,
                            "evidence_penalty_scale": evidence_scale,
                            "m_multiplier": m_multiplier,
                            "uncertainty_cap": uncertainty_cap,
                            "spearman_top200": _spearman(base_positions, sim_positions, top200_ids),
                            "kendall_top100": _kendall(base_positions, sim_positions, top100_ids),
                            "top10_overlap": len(set(top200_ids[:10]) & {x for x, r in sim_positions.items() if r <= 10}) / 10.0,
                            "top50_overlap": len(set(top200_ids[:50]) & {x for x, r in sim_positions.items() if r <= 50}) / 50.0,
                        }
                    )

    by_recipe: dict[str, dict] = {}
    for rid, values in positions.items():
        base_rank = base_positions.get(rid, values[0])
        std = pstdev(values) if len(values) > 1 else 0.0
        scale = max(2.0, base_rank * 0.10 + 2.0)
        confidence = max(0.0, min(1.0, 1.0 / (1.0 + std / scale)))
        by_recipe[rid] = {
            "rank_confidence": confidence,
            "rank_stddev": std,
            "rank_range_low": min(values),
            "rank_range_high": max(values),
            "top10_frequency": top10_hits[rid] / simulations,
            "top50_frequency": top50_hits[rid] / simulations,
            "simulation_count": simulations,
        }

    spearman_values = [x["spearman_top200"] for x in simulation_metrics if x["spearman_top200"] is not None]
    kendall_values = [x["kendall_top100"] for x in simulation_metrics if x["kendall_top100"] is not None]
    summary = {
        "simulation_count": simulations,
        "mean_spearman_top200": mean(spearman_values) if spearman_values else None,
        "min_spearman_top200": min(spearman_values) if spearman_values else None,
        "mean_kendall_top100": mean(kendall_values) if kendall_values else None,
        "min_kendall_top100": min(kendall_values) if kendall_values else None,
        "mean_top10_overlap": mean(x["top10_overlap"] for x in simulation_metrics) if simulation_metrics else None,
        "mean_top50_overlap": mean(x["top50_overlap"] for x in simulation_metrics) if simulation_metrics else None,
        "simulations": simulation_metrics,
    }
    return by_recipe, summary


def bayesian_rank(
    state: dict,
    stale_days: int = 14,
    history_limit: int = 168,
    empirical_calibration: dict[str, dict] | None = None,
    historical_metrics: dict[str, dict] | None = None,
) -> tuple[list[dict], dict]:
    current = _eligible_current(state, stale_days)
    current, deduped, duplicate_rows = dedupe_current(current, detailed=True)
    if not current:
        return [], {
            "global_prior": 0.0,
            "volume_prior_m": 0.0,
            "candidate_count": 0,
            "deduplicated_count": deduped,
            "source_adjustments": {},
            "category_baselines": {},
            "duplicate_groups": duplicate_rows,
            "robustness": {"simulation_count": 0},
        }

    ranked, scored_method = _score_current(current, empirical_calibration)
    robustness_by_recipe, robustness_summary = _robustness(current, ranked, empirical_calibration)

    previous_snapshot = state.get("rank_history", [])[-1] if state.get("rank_history") else None
    prev = {x["recipe_id"]: int(x["rank"]) for x in (previous_snapshot or {}).get("top200", (previous_snapshot or {}).get("top50", []))}
    historical_metrics = historical_metrics or {}

    for row in ranked:
        item = row.pop("_source_item")
        rid = row["recipe_id"]
        row.update(robustness_by_recipe.get(rid, {}))
        row.update(historical_metrics.get(rid, {}))
        raw_rating = float(row["rating"])
        previous_count = item.get("previous_rating_count")
        previous_seen = parse_dt(item.get("previous_seen_at"))
        current_seen = parse_dt(item.get("last_seen_at") or item.get("retrieved_at"))
        review_velocity_per_day = None
        if previous_count is not None and previous_seen and current_seen and current_seen > previous_seen:
            days = (current_seen - previous_seen).total_seconds() / 86400.0
            if days > 0:
                review_velocity_per_day = (int(row["rating_count"]) - int(previous_count)) / days
        row["rating_change"] = None if item.get("previous_rating") is None else raw_rating - float(item.get("previous_rating"))
        row["review_count_change"] = None if previous_count is None else int(row["rating_count"]) - int(previous_count)
        row["review_velocity_per_day"] = review_velocity_per_day
        row["evidence_grade"] = evidence_grade(item)
        row["previous_rank"] = prev.get(rid)
        row["movement"] = prev[rid] - row["rank"] if rid in prev else None
        row["rank_provenance"] = (
            f"Raw {row['rating']:.3f}; source/category adjustment {-row['source_bias']:+.3f}; "
            f"posterior {row['posterior_mean']:.3f}; uncertainty -{row['uncertainty_penalty']:.3f} "
            f"({row['uncertainty_method']}); evidence -{row['evidence_penalty']:.3f}; final {row['hierarchical_score']:.3f}."
        )
        if rid in state.get("recipes", {}):
            state["recipes"][rid]["last_rank"] = row["rank"]

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
                "rank_confidence": x.get("rank_confidence"),
            }
            for x in ranked[:200]
        ],
    }
    history = state.setdefault("rank_history", [])
    history.append(snapshot)
    if len(history) > history_limit:
        del history[:-history_limit]

    return ranked, {
        "global_prior": scored_method["global_prior"],
        "base_volume_prior_m": scored_method["base_volume_prior_m"],
        "volume_prior_m": scored_method["volume_prior_m"],
        "candidate_count": len(current),
        "deduplicated_count": deduped,
        "stale_days": stale_days,
        "history_snapshots": len(history),
        "category_baselines": scored_method["category_baselines"],
        "source_adjustments": scored_method["source_adjustments"],
        "duplicate_groups": duplicate_rows,
        "max_source_bias": MAX_SOURCE_BIAS,
        "robustness": robustness_summary,
        "formula": "hierarchical_score = BayesianPosterior(category-aware capped source adjustment) - calibrated uncertainty - evidence penalty",
    }
