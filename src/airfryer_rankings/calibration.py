from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from statistics import pstdev

from .models import parse_dt

VOLUME_BUCKETS = (
    (0, 24, "0-24"),
    (25, 99, "25-99"),
    (100, 499, "100-499"),
    (500, 1999, "500-1999"),
    (2000, 999999999, "2000+"),
)


def volume_bucket(count: int) -> str:
    for lo, hi, label in VOLUME_BUCKETS:
        if lo <= int(count) <= hi:
            return label
    return "2000+"


def build_empirical_uncertainty(observations: list[dict], min_pairs: int = 30) -> dict[str, dict]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in observations:
        rid = str(row.get("recipe_id") or "")
        timestamp = parse_dt(row.get("timestamp"))
        if not rid or not timestamp:
            continue
        try:
            rating = float(row.get("rating"))
            count = int(row.get("rating_count"))
        except Exception:
            continue
        grouped[rid].append({"timestamp": timestamp, "rating": rating, "rating_count": count})

    deltas: dict[str, list[float]] = defaultdict(list)
    for rows in grouped.values():
        rows.sort(key=lambda x: x["timestamp"])
        for previous, current in zip(rows, rows[1:]):
            if current["timestamp"] <= previous["timestamp"]:
                continue
            bucket = volume_bucket(max(previous["rating_count"], current["rating_count"]))
            deltas[bucket].append(current["rating"] - previous["rating"])

    result: dict[str, dict] = {}
    for _, _, label in VOLUME_BUCKETS:
        values = deltas.get(label, [])
        if values:
            rmse = math.sqrt(sum(x * x for x in values) / len(values))
            sigma = pstdev(values) if len(values) > 1 else abs(values[0])
        else:
            rmse = None
            sigma = None
        result[label] = {
            "bucket": label,
            "sample_pairs": len(values),
            "rating_delta_rmse": rmse,
            "rating_delta_sigma": sigma,
            "empirical_95_penalty": min(0.25, 1.96 * rmse) if rmse is not None else None,
            "ready": len(values) >= min_pairs,
            "min_pairs": min_pairs,
        }
    return result


def empirical_penalty(calibration: dict[str, dict] | None, rating_count: int) -> tuple[float | None, str]:
    if not calibration:
        return None, "theoretical"
    row = calibration.get(volume_bucket(rating_count)) or {}
    if row.get("ready") and row.get("empirical_95_penalty") is not None:
        return float(row["empirical_95_penalty"]), "empirical_history"
    return None, "theoretical"


def _earliest_within(rows: list[dict], now: datetime, days: int) -> dict | None:
    threshold = now - timedelta(days=days)
    eligible = [x for x in rows if x["timestamp"] >= threshold]
    return min(eligible, key=lambda x: x["timestamp"]) if eligible else None


def build_historical_metrics(
    observations: list[dict],
    ranking_records: list[dict],
    now: datetime | None = None,
) -> dict[str, dict]:
    now = now or datetime.now(timezone.utc)
    obs_by_recipe: dict[str, list[dict]] = defaultdict(list)
    for row in observations:
        rid = str(row.get("recipe_id") or "")
        timestamp = parse_dt(row.get("timestamp"))
        if not rid or not timestamp:
            continue
        try:
            obs_by_recipe[rid].append(
                {
                    "timestamp": timestamp,
                    "rating": float(row.get("rating")),
                    "rating_count": int(row.get("rating_count")),
                }
            )
        except Exception:
            continue

    ranks_by_recipe: dict[str, list[dict]] = defaultdict(list)
    for row in ranking_records:
        rid = str(row.get("recipe_id") or "")
        timestamp = parse_dt(row.get("timestamp") or row.get("run_at"))
        try:
            rank = int(row.get("rank"))
        except Exception:
            continue
        if rid and timestamp:
            ranks_by_recipe[rid].append({"timestamp": timestamp, "rank": rank})

    output: dict[str, dict] = {}
    recipe_ids = set(obs_by_recipe) | set(ranks_by_recipe)
    for rid in recipe_ids:
        obs = sorted(obs_by_recipe.get(rid, []), key=lambda x: x["timestamp"])
        ranks = sorted(ranks_by_recipe.get(rid, []), key=lambda x: x["timestamp"])
        metrics: dict = {}
        if obs:
            current = obs[-1]
            seven = _earliest_within(obs, now, 7)
            thirty = _earliest_within(obs, now, 30)
            metrics["review_growth_7d"] = current["rating_count"] - seven["rating_count"] if seven and seven is not current else None
            metrics["review_growth_30d"] = current["rating_count"] - thirty["rating_count"] if thirty and thirty is not current else None
            metrics["rating_trend_30d"] = current["rating"] - thirty["rating"] if thirty and thirty is not current else None
        if ranks:
            values = [x["rank"] for x in ranks]
            metrics["peak_rank"] = min(values)
            metrics["rank_volatility"] = pstdev(values) if len(values) > 1 else 0.0
            metrics["days_in_top10"] = len({x["timestamp"].date().isoformat() for x in ranks if x["rank"] <= 10})
            metrics["days_in_top50"] = len({x["timestamp"].date().isoformat() for x in ranks if x["rank"] <= 50})
            metrics["ranking_observations"] = len(ranks)
        output[rid] = metrics
    return output


def evidence_grade(recipe: dict, now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    status = str(recipe.get("evidence_status") or "")
    confidence = float(recipe.get("evidence_confidence", 0.60))
    count = int(recipe.get("rating_count", 0))
    seen = parse_dt(recipe.get("last_seen_at") or recipe.get("retrieved_at"))
    age_days = (now - seen).total_seconds() / 86400.0 if seen else 9999.0

    if status == "conflict" or confidence < 0.60:
        return "F"
    if status == "legacy_unverified":
        return "C-"
    if status == "verified" and confidence >= 0.95 and count >= 1000 and age_days <= 7:
        return "A+"
    if status == "verified" and confidence >= 0.95 and count >= 250 and age_days <= 14:
        return "A"
    if confidence >= 0.80 and count >= 100 and age_days <= 14:
        return "B+"
    if confidence >= 0.65 and count >= 50 and age_days <= 14:
        return "B"
    if confidence >= 0.60 and age_days <= 30:
        return "C"
    return "D"
