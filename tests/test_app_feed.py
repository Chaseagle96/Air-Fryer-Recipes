from __future__ import annotations

import json
from pathlib import Path

from airfryer_rankings.app_feed import build_app_recipe, write_app_feed
from airfryer_rankings.dashboard import write_dashboard


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
        "last_seen_at": "2026-08-19T00:00:00Z",
    }


def sample_state_recipe(
    recipe_id: str,
    *,
    last_seen_at: str = "2026-08-19T00:00:00Z",
    rating_count: int = 10,
    evidence_confidence: float = 0.8,
    evidence_status: str = "verified",
) -> dict:
    return {
        "recipe_id": recipe_id,
        "title": f"State {recipe_id}",
        "source": "state.example",
        "url": f"https://state.example/{recipe_id}",
        "canonical_url": f"https://state.example/{recipe_id}",
        "image_url": f"https://images.example.com/{recipe_id}.jpg",
        "author": "State Author",
        "categories": ["Dinner"],
        "ingredients": ["1 onion"],
        "instructions": ["Internal publisher instruction prose."],
        "normalized_rating": 4.4,
        "rating_count": rating_count,
        "evidence_confidence": evidence_confidence,
        "evidence_status": evidence_status,
        "last_seen_at": last_seen_at,
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
    assert payload["discover_eligible"] is True
    assert payload["serveability"] == "discover"
    assert "instructions" not in payload


def test_mobile_feed_paginates_entire_ranked_corpus(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("RECIPE_INTELLIGENCE_VERTICAL", "Air Fryer")
    monkeypatch.setenv("RECIPE_INTELLIGENCE_VERTICAL_SLUG", "air_fryer")
    ranked = [sample_ranked(index) for index in range(205)]
    manifest_path = Path(write_app_feed(tmp_path, "2026-08-19T00:00:00Z", ranked, 40, page_size=100))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["recipe_count"] == 205
    assert manifest["ranked_recipe_count"] == 205
    assert manifest["corpus_recipe_count"] == 205
    assert [page["count"] for page in manifest["pages"]] == [100, 100, 5]
    assert [page["count"] for page in manifest["corpus_pages"]] == [100, 100, 5]
    first = json.loads((tmp_path / "api" / manifest["pages"][0]["path"]).read_text(encoding="utf-8"))
    last = json.loads((tmp_path / "api" / manifest["pages"][-1]["path"]).read_text(encoding="utf-8"))
    assert first["recipes"][0]["rank"] == 1
    assert last["recipes"][-1]["rank"] == 205
    assert first["recipes"][0]["image_url"].startswith("https://")


def test_full_corpus_retains_unranked_records_with_serveability_metadata(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("RECIPE_INTELLIGENCE_VERTICAL", "Air Fryer")
    monkeypatch.setenv("RECIPE_INTELLIGENCE_VERTICAL_SLUG", "air_fryer")
    ranked = [sample_ranked(0)]
    ranked_state = sample_state_recipe("recipe-0")
    exploratory = sample_state_recipe("explore-me", rating_count=0, evidence_confidence=0.4)
    stale = sample_state_recipe("stale-one", last_seen_at="2026-07-01T00:00:00Z")
    conflict = sample_state_recipe("conflict-one", evidence_status="conflict")
    manifest_path = Path(
        write_app_feed(
            tmp_path,
            "2026-08-19T00:00:00Z",
            ranked,
            40,
            corpus=[ranked_state, exploratory, stale, conflict],
            catalog_url_count=4000,
            page_size=100,
        )
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["recipe_count"] == 1
    assert manifest["corpus_recipe_count"] == 4
    assert manifest["catalog_url_count"] == 4000
    assert manifest["corpus_status_counts"] == {"archive": 1, "discover": 1, "explore": 1, "suppressed": 1}

    corpus_page = json.loads((tmp_path / "api" / manifest["corpus_pages"][0]["path"]).read_text(encoding="utf-8"))
    by_id = {row["recipe_id"]: row for row in corpus_page["recipes"]}
    assert by_id["recipe-0"]["is_ranked"] is True
    assert by_id["recipe-0"]["serveability"] == "discover"
    assert by_id["explore-me"]["is_ranked"] is False
    assert by_id["explore-me"]["explore_eligible"] is True
    assert "no_rating_evidence" in by_id["explore-me"]["status_reasons"]
    assert "low_evidence" in by_id["explore-me"]["status_reasons"]
    assert by_id["stale-one"]["serveability"] == "archive"
    assert by_id["conflict-one"]["serveability"] == "suppressed"
    assert all("instructions" not in row for row in corpus_page["recipes"])


def test_production_dashboard_backfills_mobile_corpus_from_existing_state(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("RECIPE_INTELLIGENCE_VERTICAL", "Air Fryer")
    monkeypatch.setenv("RECIPE_INTELLIGENCE_VERTICAL_SLUG", "air_fryer")
    (tmp_path / "data").mkdir()
    state = {
        "recipes": {
            "recipe-0": sample_state_recipe("recipe-0"),
            "unranked": sample_state_recipe("unranked", rating_count=0),
        },
        "url_catalog": {"a": {}, "b": {}, "c": {}},
    }
    (tmp_path / "data" / "state.json").write_text(json.dumps(state), encoding="utf-8")

    write_dashboard("docs", "2026-08-19T00:00:00Z", [sample_ranked(0)], [], [], {"stale_days": 14}, 40)
    manifest = json.loads((tmp_path / "docs" / "api" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["recipe_count"] == 1
    assert manifest["corpus_recipe_count"] == 2
    assert manifest["catalog_url_count"] == 3
