from __future__ import annotations

import math

from ..model_config import ModelParameters


def percentile(values: list[int], quantile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    position = (len(ordered) - 1) * quantile
    low = math.floor(position)
    high = math.ceil(position)
    if low == high:
        return float(ordered[low])
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def global_prior(current: list[dict]) -> float:
    if not current:
        return 0.0
    weights = [math.sqrt(max(1, int(item["rating_count"]))) for item in current]
    ratings = [float(item["normalized_rating"]) for item in current]
    return sum(rating * weight for rating, weight in zip(ratings, weights, strict=True)) / max(1e-9, sum(weights))


def volume_prior_m(current: list[dict], params: ModelParameters) -> tuple[float, float]:
    counts = [int(item["rating_count"]) for item in current]
    base = max(params.minimum_volume_prior, percentile(counts, params.volume_prior_quantile))
    return base, max(1.0, base * params.volume_prior_multiplier)


def bayesian_posterior(rating: float, rating_count: int, prior: float, prior_strength: float) -> float:
    count = max(0, int(rating_count))
    strength = max(1e-9, float(prior_strength))
    return (count / (count + strength)) * float(rating) + (strength / (count + strength)) * float(prior)
