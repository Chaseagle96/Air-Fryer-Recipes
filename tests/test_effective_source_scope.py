from airfryer_rankings.core import SourceConfig, bayesian_rank, select_refresh_targets


def _recipe(recipe_id: str, source: str, rating: float, count: int) -> dict:
    return {
        "recipe_id": recipe_id,
        "title": f"Air Fryer {recipe_id}",
        "source": source,
        "url": f"https://{source}/{recipe_id}",
        "canonical_url": f"https://{source}/{recipe_id}",
        "normalized_rating": rating,
        "rating_count": count,
        "evidence_confidence": 0.9,
        "evidence_status": "verified",
        "last_seen_at": "2026-08-19T12:00:00+00:00",
        "retrieved_at": "2026-08-19T12:00:00+00:00",
        "ingredients": ["potatoes", "salt"],
        "instructions": ["Air fry until crisp"],
        "categories": ["Potatoes"],
    }


def test_refresh_scope_immediately_evicts_suspended_source_from_ranking() -> None:
    state = {
        "recipes": {
            "active": _recipe("active", "active.example", 4.8, 500),
            "suspended": _recipe("suspended", "suspended.example", 5.0, 5000),
        },
        "url_catalog": {
            "https://active.example/active": {
                "url": "https://active.example/active",
                "source": "active.example",
                "recipe_id": "active",
            },
            "https://suspended.example/suspended": {
                "url": "https://suspended.example/suspended",
                "source": "suspended.example",
                "recipe_id": "suspended",
            },
        },
        "rank_history": [],
    }

    targets = select_refresh_targets(
        state,
        [SourceConfig("active.example")],
        "hourly",
        hourly_limit=10,
    )
    assert state["effective_source_domains"] == ["active.example"]
    assert {target["source"] for target in targets} == {"active.example"}

    ranked, _ = bayesian_rank(state, stale_days=10000)
    assert [row["source"] for row in ranked] == ["active.example"]


def test_explicit_allowed_sources_override_persisted_scope() -> None:
    state = {
        "recipes": {
            "one": _recipe("one", "one.example", 4.8, 500),
            "two": _recipe("two", "two.example", 4.9, 600),
        },
        "effective_source_domains": ["one.example"],
        "rank_history": [],
    }

    ranked, _ = bayesian_rank(state, stale_days=10000, allowed_sources={"two.example"})
    assert [row["source"] for row in ranked] == ["two.example"]
