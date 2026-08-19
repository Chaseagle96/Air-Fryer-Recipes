from __future__ import annotations

import math

from ..calibration import empirical_penalty

EMPIRICAL_THEORETICAL_FLOOR_FRACTION = 0.25


def histogram_penalty(histogram: dict, rating_count: int, prior_strength: float, cap: float) -> float | None:
    pairs: list[tuple[float, int]] = []
    for star, count in (histogram or {}).items():
        try:
            pairs.append((float(star), int(count)))
        except (TypeError, ValueError):
            continue
    total = sum(count for _, count in pairs)
    if total <= 1:
        return None
    histogram_mean = sum(star * count for star, count in pairs) / total
    variance = sum(((star - histogram_mean) ** 2) * count for star, count in pairs) / max(1, total - 1)
    return min(cap, 1.96 * math.sqrt(max(0.0, variance) / max(1.0, rating_count + prior_strength)))


def uncertainty_penalty(
    item: dict,
    rating_count: int,
    prior_strength: float,
    cap: float,
    calibration: dict[str, dict] | None,
) -> tuple[float, str]:
    histogram_value = histogram_penalty(item.get("rating_histogram") or {}, rating_count, prior_strength, cap)
    if histogram_value is not None:
        return histogram_value, "rating_histogram"

    theoretical = min(cap, 1.96 * 2.5 / math.sqrt(max(1.0, rating_count + prior_strength)))
    empirical_value, _ = empirical_penalty(calibration, rating_count)
    if empirical_value is not None:
        # Published ratings are typically rounded. A run of unchanged aggregates can
        # therefore underestimate latent uncertainty even in a mature history. Keep
        # a count-sensitive fraction of the conservative theoretical penalty as a
        # floor while allowing real longitudinal evidence to reduce uncertainty.
        floor = EMPIRICAL_THEORETICAL_FLOOR_FRACTION * theoretical
        return min(cap, max(empirical_value, floor)), "empirical_history_blended"
    return theoretical, "theoretical_max_variance"
