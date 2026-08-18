from __future__ import annotations

from hypothesis import given, strategies as st

from airfryer_rankings.model_config import ModelParameters
from airfryer_rankings.ranking_components import bayesian_posterior, score_current, uncertainty_penalty


@given(
    rating=st.floats(min_value=3.0, max_value=5.0, allow_nan=False, allow_infinity=False),
    prior=st.floats(min_value=3.0, max_value=5.0, allow_nan=False, allow_infinity=False),
    low_count=st.integers(min_value=1, max_value=1000),
    extra=st.integers(min_value=1, max_value=10000),
    strength=st.floats(min_value=1.0, max_value=5000.0, allow_nan=False, allow_infinity=False),
)
def test_more_evidence_moves_posterior_toward_observed_rating(rating, prior, low_count, extra, strength):
    low = bayesian_posterior(rating, low_count, prior, strength)
    high = bayesian_posterior(rating, low_count + extra, prior, strength)
    assert abs(high - rating) <= abs(low - rating) + 1e-12


@given(
    low_count=st.integers(min_value=1, max_value=10000),
    extra=st.integers(min_value=1, max_value=50000),
)
def test_theoretical_uncertainty_never_increases_with_more_reviews(low_count, extra):
    item = {"rating_histogram": {}}
    low, _ = uncertainty_penalty(item, low_count, 50.0, 0.25, None)
    high, _ = uncertainty_penalty(item, low_count + extra, 50.0, 0.25, None)
    assert high <= low + 1e-12


@given(
    high_confidence=st.floats(min_value=0.61, max_value=1.0, allow_nan=False, allow_infinity=False),
    gap=st.floats(min_value=0.001, max_value=0.30, allow_nan=False, allow_infinity=False),
)
def test_lower_evidence_confidence_cannot_improve_identical_recipe_score(high_confidence, gap):
    low_confidence = max(0.60, high_confidence - gap)
    base = {
        "recipe_id": "a",
        "title": "Air Fryer Chicken",
        "source": "example.com",
        "url": "https://example.com/a",
        "canonical_url": "https://example.com/a",
        "normalized_rating": 4.8,
        "rating_count": 500,
        "last_seen_at": "2026-08-18T20:00:00+00:00",
        "evidence_status": "schema_only",
        "categories": ["Chicken"],
    }
    high_rows, _ = score_current([{**base, "evidence_confidence": high_confidence}], None, ModelParameters())
    low_rows, _ = score_current([{**base, "evidence_confidence": low_confidence}], None, ModelParameters())
    assert low_rows[0]["hierarchical_score"] <= high_rows[0]["hierarchical_score"] + 1e-12


@given(confidence=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False))
def test_rank_confidence_domain_is_bounded(confidence):
    assert 0.0 <= confidence <= 1.0
