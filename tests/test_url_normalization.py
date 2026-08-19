from __future__ import annotations

from airfryer_rankings.url_normalization import normalize_discovered_url, normalize_url_catalog


def test_discovered_url_removes_tracking_share_and_fragment_but_preserves_semantic_query() -> None:
    value = normalize_discovered_url(
        "HTTPS://Example.COM/air-fryer-chicken/?utm_source=newsletter&servings=4&share=facebook&fbclid=abc#recipe"
    )
    assert value == "https://example.com/air-fryer-chicken/?servings=4"


def test_catalog_aliases_coalesce_without_losing_useful_metadata() -> None:
    state = {
        "url_catalog": {
            "https://example.com/air-fryer-chicken/?share=facebook": {
                "url": "https://example.com/air-fryer-chicken/?share=facebook",
                "source": "example.com",
                "first_discovered": "2026-08-18T00:00:00+00:00",
                "last_discovered": "2026-08-18T01:00:00+00:00",
                "last_checked": "2026-08-18T01:00:00+00:00",
                "recipe_id": "recipe-1",
                "priority": "stable",
                "etag": "old-etag",
                "missing_count": 0,
            },
            "https://example.com/air-fryer-chicken/?utm_medium=social": {
                "url": "https://example.com/air-fryer-chicken/?utm_medium=social",
                "source": "example.com",
                "first_discovered": "2026-08-19T00:00:00+00:00",
                "last_discovered": "2026-08-19T02:00:00+00:00",
                "last_checked": "2026-08-19T02:00:00+00:00",
                "priority": "modified",
                "lastmod": "2026-08-19T01:30:00+00:00",
                "missing_count": 1,
            },
        }
    }

    result = normalize_url_catalog(state)

    assert result == {"before": 2, "after": 1, "aliases_coalesced": 1, "urls_rewritten": 2}
    assert list(state["url_catalog"]) == ["https://example.com/air-fryer-chicken/"]
    merged = state["url_catalog"]["https://example.com/air-fryer-chicken/"]
    assert merged["first_discovered"] == "2026-08-18T00:00:00+00:00"
    assert merged["last_discovered"] == "2026-08-19T02:00:00+00:00"
    assert merged["last_checked"] == "2026-08-19T02:00:00+00:00"
    assert merged["recipe_id"] == "recipe-1"
    assert merged["priority"] == "modified"
    assert merged["etag"] == "old-etag"
    assert merged["missing_count"] == 1
