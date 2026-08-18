from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from statistics import mean, pstdev

from .models import parse_dt

VOLUME_BUCKETS = (
    (0, 24, "0-24"),
    (25, 99, "25-99"),
    (100, 499, "100-499"),
    (500, 1999, "500-1999"),
    (2000, 999999999, "2000+"),
)


def volume_bucket(count: int) -> str:
    for low, high, label in VOLUME_BUCKETS:
        if low <= int(count) <= high:
            return label
    return "2000+"


def build_empirical_uncertainty(observations: list[dict], min_pairs: int = 30) -> dict[str, dict]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in observations:
        recipe_id = str(row.get("recipe_id") or "")
        timestamp = parse_dt(row.get("timestamp"))
        if not recipe_id or not timestamp:
            continue
        try:
            rating = float(row.get("rating"))
            count = int(row.get("rating_count"))
        except (TypeError, ValueError):
            continue
        grouped[recipe_id].append({"timestamp": timestamp, "rating": rating, "rating_count": count})

    deltas: dict[str, list[float]] = defaultdict(list)
    for rows in grouped.values():
        rows.sort(key=lambda item: item["timestamp"])
        for previous, current in zip(rows, rows[1:], strict=False):
            if current["timestamp"] <= previous["timestamp"]:
                continue
            bucket = volume_bucket(max(previous["rating_count"], current["rating_count"]))
            deltas[bucket].append(current["rating"] - previous["rating"])

    result: dict[str, dict] = {}
    for _, _, label in VOLUME_BUCKETS:
        values = deltas.get(label, [])
        if values:
            rmse = math.sqrt(sum(value * value for value in values) / len(values))
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
    eligible = [row for row in rows if row["timestamp"] >= threshold]
    return min(eligible, key=lambda row: row["timestamp"]) if eligible else None


def _linear_slope(rows: list[dict], key: str) -> float | None:
    if len(rows) < 2:
        return None
    origin = rows[0]["timestamp"]
    xs = [(row["timestamp"] - origin).total_seconds() / 86400.0 for row in rows]
    ys = [float(row[key]) for row in rows]
    mean_x = mean(xs)
    mean_y = mean(ys)
    denominator = sum((x - mean_x) ** 2 for x in xs)
    if denominator <= 0:
        return None
    return sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=True)) / denominator


def _rate_between(start: dict | None, end: dict | None) -> float | None:
    if not start or not end or end["timestamp"] <= start["timestamp"]:
        return None
    days = (end["timestamp"] - start["timestamp"]).total_seconds() / 86400.0
    return (int(end["rating_count"]) - int(start["rating_count"])) / days if days > 0 else None


def _change_point(rows: list[dict]) -> tuple[bool, float | None]:
    if len(rows) < 6:
        return False, None
    recent = rows[-3:]
    previous = rows[-6:-3]
    delta = mean(float(row["rating"]) for row in recent) - mean(float(row["rating"]) for row in previous)
    return abs(delta) >= 0.05, delta


def build_historical_metrics(
    observations: list[dict],
    ranking_records: list[dict],
    now: datetime | None = None,
) -> dict[str, dict]:
    now = now or datetime.now(timezone.utc)
    observations_by_recipe: dict[str, list[dict]] = defaultdict(list)
    for row in observations:
        recipe_id = str(row.get("recipe_id") or "")
        timestamp = parse_dt(row.get("timestamp"))
        if not recipe_id or not timestamp:
            continue
        try:
            observations_by_recipe[recipe_id].append(
                {
                    "timestamp": timestamp,
                    "rating": float(row.get("rating")),
                    "rating_count": int(row.get("rating_count")),
                    "page_hash": str(row.get("page_hash") or ""),
                }
            )
        except (TypeError, ValueError):
            continue

    ranks_by_recipe: dict[str, list[dict]] = defaultdict(list)
    for row in ranking_records:
        recipe_id = str(row.get("recipe_id") or "")
        timestamp = parse_dt(row.get("timestamp") or row.get("run_at"))
        try:
            rank = int(row.get("rank"))
        except (TypeError, ValueError):
            continue
        if recipe_id and timestamp:
            ranks_by_recipe[recipe_id].append({"timestamp": timestamp, "rank": rank})

    output: dict[str, dict] = {}
    recipe_ids = set(observations_by_recipe) | set(ranks_by_recipe)
    for recipe_id in recipe_ids:
        observations_for_recipe = sorted(observations_by_recipe.get(recipe_id, []), key=lambda row: row["timestamp"])
        ranks = sorted(ranks_by_recipe.get(recipe_id, []), key=lambda row: row["timestamp"])
        metrics: dict = {}
        if observations_for_recipe:
            current = observations_for_recipe[-1]
            seven = _earliest_within(observations_for_recipe, now, 7)
            fourteen = _earliest_within(observations_for_recipe, now, 14)
            thirty = _earliest_within(observations_for_recipe, now, 30)
            metrics["review_growth_7d"] = (
                current["rating_count"] - seven["rating_count"] if seven and seven is not current else None
            )
            metrics["review_growth_30d"] = (
                current["rating_count"] - thirty["rating_count"] if thirty and thirty is not current else None
            )
            metrics["rating_trend_30d"] = current["rating"] - thirty["rating"] if thirty and thirty is not current else None
            last_30 = [row for row in observations_for_recipe if row["timestamp"] >= now - timedelta(days=30)]
            metrics["rating_slope_30d_per_day"] = _linear_slope(last_30, "rating")
            metrics["review_slope_30d_per_day"] = _linear_slope(last_30, "rating_count")
            metrics["review_velocity_7d"] = _rate_between(seven, current)
            if fourteen and seven and fourteen["timestamp"] < seven["timestamp"]:
                previous_velocity = _rate_between(fourteen, seven)
            else:
                previous_velocity = None
            metrics["review_velocity_previous_7d"] = previous_velocity
            metrics["review_acceleration_14d"] = (
                metrics["review_velocity_7d"] - previous_velocity
                if metrics["review_velocity_7d"] is not None and previous_velocity is not None
                else None
            )
            hashes = [(row["timestamp"], row["page_hash"]) for row in last_30 if row["page_hash"]]
            changes = [
                current_hash
                for previous_hash, current_hash in zip(hashes, hashes[1:], strict=False)
                if previous_hash[1] != current_hash[1]
            ]
            metrics["page_change_count_30d"] = len(changes)
            metrics["last_material_page_change_at"] = changes[-1][0].isoformat() if changes else None
            change_point, change_delta = _change_point(last_30)
            metrics["rating_change_point_30d"] = change_point
            metrics["rating_change_point_delta"] = change_delta
        if ranks:
            rank_values = [row["rank"] for row in ranks]
            metrics["peak_rank"] = min(rank_values)
            metrics["rank_volatility"] = pstdev(rank_values) if len(rank_values) > 1 else 0.0
            metrics["days_in_top10"] = len({row["timestamp"].date().isoformat() for row in ranks if row["rank"] <= 10})
            metrics["days_in_top50"] = len({row["timestamp"].date().isoformat() for row in ranks if row["rank"] <= 50})
            metrics["ranking_observations"] = len(ranks)
        output[recipe_id] = metrics
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
