from __future__ import annotations

import json
from pathlib import Path

from airfryer_rankings.model_config import ModelParameters
from airfryer_rankings.ranking_components import score_current


def _recipe(recipe_id: str, rating: float, count: int, confidence: float) -> dict:
    return {
        "recipe_id": recipe_id,
        "title": f"Air Fryer Chicken {recipe_id.upper()}",
        "source": "example.com",
        "url": f"https://example.com/{recipe_id}",
        "canonical_url": f"https://example.com/{recipe_id}",
        "normalized_rating": rating,
        "rating_count": count,
        "evidence_confidence": confidence,
        "evidence_status": "verified" if confidence >= 0.95 else "schema_only",
        "last_seen_at": "2026-08-18T20:00:00+00:00",
        "categories": ["Chicken"],
        "rating_histogram": {},
    }


def test_golden_ranking_output_only_changes_intentionally():
    expected = json.loads(Path("tests/fixtures/golden_ranking.json").read_text(encoding="utf-8"))["expected"]
    current = [
        _recipe("a", 4.9, 5000, 1.0),
        _recipe("b", 5.0, 100, 1.0),
        _recipe("c", 4.8, 1000, 0.65),
        _recipe("d", 4.7, 10000, 1.0),
        _recipe("e", 4.95, 20, 1.0),
    ]
    ranked, _ = score_current(current, calibration=None, params=ModelParameters())
    actual = [
        {
            "recipe_id": row["recipe_id"],
            "rank": row["rank"],
            "hierarchical_score": round(float(row["hierarchical_score"]), 9),
        }
        for row in ranked
    ]
    assert actual == expected
