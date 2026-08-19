from airfryer_rankings.core import SourceConfig, bayesian_rank, select_refresh_targets


def _recipe(
    recipe_id: str,
    source: str,
    rating: float,
    count: int,
    *,
    title: str | None = None,
    url: str | None = None,
) -> dict:
    recipe_url = url or f"https://{source}/{recipe_id}"
    return {
        "recipe_id": recipe_id,
        "title": title or f"Air Fryer {recipe_id}",
        "source": source,
        "url": recipe_url,
        "canonical_url": recipe_url,
        "normalized_rating": rating,
        "rating_count": count,
        "evidence_confidence": 0.9,
        "evidence_status": "verified",
        "last_seen_at": "2026-08-19T12:00:00+00:00",
        "retrieved_at": "2026-08-19T12:00:00+00:00",
        "ingredients": ["potatoes", "salt"],
        "instructions": ["Cook until ready"],
        "categories": ["Dinner"],
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


def test_slow_cooker_scope_evicts_retained_cross_vertical_recipe_before_scoring() -> None:
    state = {
        "recipes": {
            "birria": _recipe(
                "birria",
                "budgetbytes.com",
                5.0,
                50000,
                title="Birria Tacos",
                url="https://www.budgetbytes.com/birria-tacos/",
            ),
            "slow-lemon": _recipe(
                "slow-lemon",
                "skinnytaste.com",
                4.9,
                1000,
                title="Slow Cooker Lemon Feta Drumsticks",
                url="https://www.skinnytaste.com/slow-cooker-lemon-feta-chicken/",
            ),
        },
        "effective_source_domains": ["budgetbytes.com", "skinnytaste.com"],
        "rank_history": [],
    }

    ranked, method = bayesian_rank(
        state,
        stale_days=10000,
        model_config_path="config/verticals/slow_cooker/model.yaml",
    )

    assert [row["recipe_id"] for row in ranked] == ["slow-lemon"]
    assert method["candidate_count"] == 1
    assert "budgetbytes.com" not in method["source_adjustments"]
