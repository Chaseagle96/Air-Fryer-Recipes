from datetime import datetime, timedelta, timezone

import pytest

from airfryer_rankings.calibration import build_empirical_uncertainty
from airfryer_rankings.ranking_components.uncertainty import uncertainty_penalty


def _observation(recipe_id: str, timestamp: datetime, rating: float, count: int) -> dict:
    return {
        "recipe_id": recipe_id,
        "timestamp": timestamp.isoformat(),
        "rating": rating,
        "rating_count": count,
    }


def test_hourly_repeated_observations_do_not_create_empirical_readiness():
    start = datetime(2026, 8, 18, tzinfo=timezone.utc)
    observations = []
    for recipe_index in range(12):
        for hour in range(6):
            observations.append(
                _observation(
                    f"r{recipe_index}",
                    start + timedelta(hours=hour),
                    4.8,
                    30 + hour,
                )
            )

    calibration = build_empirical_uncertainty(observations)
    bucket = calibration["25-99"]
    assert bucket["sample_pairs"] == 0
    assert bucket["unique_recipes"] == 0
    assert bucket["ready"] is False
    assert bucket["meets_pair_count"] is False


def test_many_daily_pairs_still_require_several_weeks_of_history():
    start = datetime(2026, 8, 1, tzinfo=timezone.utc)
    observations = []
    for recipe_index in range(10):
        for day in range(4):
            observations.append(
                _observation(
                    f"r{recipe_index}",
                    start + timedelta(days=day),
                    4.8 + (0.01 if day % 2 else 0.0),
                    30 + day * 5,
                )
            )

    calibration = build_empirical_uncertainty(observations)
    bucket = calibration["25-99"]
    assert bucket["sample_pairs"] == 30
    assert bucket["unique_recipes"] == 10
    assert bucket["history_span_days"] == pytest.approx(3.0)
    assert bucket["meets_pair_count"] is True
    assert bucket["meets_unique_recipe_count"] is True
    assert bucket["meets_history_span"] is False
    assert bucket["ready"] is False


def test_multiweek_review_growth_can_activate_empirical_uncertainty():
    start = datetime(2026, 7, 1, tzinfo=timezone.utc)
    observations = []
    ratings = (4.70, 4.72, 4.69, 4.73)
    for recipe_index in range(10):
        for step, rating in enumerate(ratings):
            observations.append(
                _observation(
                    f"r{recipe_index}",
                    start + timedelta(days=step * 7),
                    rating + recipe_index * 0.001,
                    30 + step * 10,
                )
            )

    calibration = build_empirical_uncertainty(observations)
    bucket = calibration["25-99"]
    assert bucket["sample_pairs"] == 30
    assert bucket["unique_recipes"] == 10
    assert bucket["history_span_days"] == pytest.approx(21.0)
    assert bucket["minimum_pair_gap_hours_observed"] >= 24.0
    assert bucket["rating_delta_rmse"] is not None and bucket["rating_delta_rmse"] > 0
    assert bucket["ready"] is True


def test_ready_empirical_zero_delta_retains_count_sensitive_uncertainty_floor():
    calibration = {
        "25-99": {
            "bucket": "25-99",
            "ready": True,
            "empirical_95_penalty": 0.0,
        }
    }
    penalty, method = uncertainty_penalty(
        {},
        rating_count=36,
        prior_strength=50.0,
        cap=0.25,
        calibration=calibration,
    )
    assert method == "empirical_history_blended"
    assert penalty == pytest.approx(0.0625)
    assert penalty > 0
