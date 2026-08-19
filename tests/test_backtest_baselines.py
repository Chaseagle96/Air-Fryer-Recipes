from datetime import datetime, timedelta, timezone

from airfryer_rankings.backtesting import BASELINE_FAMILIES, run_historical_backtest
from airfryer_rankings.model_config import ModelParameters


def test_backtest_reports_simple_model_family_controls_without_promoting_them():
    active = ModelParameters()
    payload = {
        "promotion_policy": {
            "automatic_parameter_promotion": False,
            "minimum_history_days": 30,
            "minimum_backtest_windows": 1,
            "minimum_backtest_recipes": 5,
        },
        "backtest_grid": {
            "max_source_bias": [0.15],
            "evidence_penalty_scale": [0.20],
            "source_prior_strength": [20.0],
            "category_prior_strength": [20.0],
            "uncertainty_cap": [0.25],
            "volume_prior_multiplier": [1.0],
        },
    }
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    observations = []
    for index in range(10):
        for day, count in ((0, 20 + index), (40, 500 + index * 10), (80, 900 + index * 20)):
            observations.append(
                {
                    "recipe_id": f"r{index}",
                    "timestamp": (start + timedelta(days=day)).isoformat(),
                    "source": "example.com",
                    "url": f"https://example.com/r{index}",
                    "title": f"Air Fryer Recipe {index}",
                    "rating": 4.35 + index * 0.05,
                    "rating_count": count,
                    "evidence_confidence": 1.0,
                    "evidence_status": "verified",
                    "categories": ["Chicken"],
                }
            )

    result = run_historical_backtest(observations, active, payload, horizons=(30,), max_windows=1)
    baseline_families = {row["model_family"] for row in result["baseline_configurations"]}
    assert baseline_families == set(BASELINE_FAMILIES)
    assert {"raw_rating", "confidence_lcb", "simple_bayesian"}.issubset(
        {row["model_family"] for row in result["configurations"]}
    )
    assert result["recommendation"] is not None
    assert result["recommendation"]["model_family"] == "hierarchical"
    assert result["automatic_parameter_promotion"] is False
