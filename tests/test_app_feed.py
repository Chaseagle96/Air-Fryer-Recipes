from __future__ import annotations

import json
from pathlib import Path

from airfryer_rankings.app_feed import build_app_recipe, write_app_feed


def sample_ranked(index: int) -> dict:
    return {
        "recipe_id": f"recipe-{index}",
        "title": f"Recipe {index}",
        "source": "example.com",
        "url": f"https://example.com/recipe-{index}",
        "canonical_url": f"https://example.com/recipe-{index}",
        "image_url": f"https://images.example.com/{index}.jpg",
        "author": "Example Author",
        "categories": "Chicken | Dinner",
        "ingredients": ["1 onion", "2 cups broth"],
        "instructions": ["Copyrighted publisher prose must not enter the mobile feed."],
        "has_instructions": True,
        "instruction_count": 6,
        "rank": index + 1,
        "rating": 4.8,
        "rating_count": 500,
        "hierarchical_score": 4.6,
        "evidence_confidence": 0.95,
        "evidence_grade": "A",
        "evidence_status": "verified",
        "rank_confidence": 0.9,
        "rank_range_low": index + 1,
        "rank_range_high": index + 3,
        "rank_provenance": "test",
    }


def test_mobile_projection_exposes_factual_content_without_instruction_prose(monkeypatch) -> None:
    monkeypatch.setenv("RECIPE_INTELLIGENCE_VERTICAL", "Slow Cooker")
    monkeypatch.setenv("RECIPE_INTELLIGENCE_VERTICAL_SLUG", "slow_cooker")
    payload = build_app_recipe(sample_ranked(0))
    assert payload["vertical_id"] == "slow_cooker"
    assert payload["image_url"].endswith("0.jpg")
    assert payload["ingredients"] == ["1 onion", "2 cups broth"]
    assert payload["categories"] == ["Chicken", "Dinner"]
    assert payload["has_instructions"] is True
    assert payload["instruction_count"] == 6
    assert "instructions" not in payload


def test_mobile_feed_paginates_entire_ranked_corpus(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("RECIPE_INTELLIGENCE_VERTICAL", "Air Fryer")
    monkeypatch.setenv("RECIPE_INTELLIGENCE_VERTICAL_SLUG", "air_fryer")
    ranked = [sample_ranked(index) for index in range(205)]
    manifest_path = Path(write_app_feed(tmp_path, "2026-08-19T00:00:00Z", ranked, 40, page_size=100))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["recipe_count"] == 205
    assert [page["count"] for page in manifest["pages"]] == [100, 100, 5]
    first = json.loads((tmp_path / "api" / manifest["pages"][0]["path"]).read_text(encoding="utf-8"))
    last = json.loads((tmp_path / "api" / manifest["pages"][-1]["path"]).read_text(encoding="utf-8"))
    assert first["recipes"][0]["rank"] == 1
    assert last["recipes"][-1]["rank"] == 205
    assert first["recipes"][0]["image_url"].startswith("https://")
