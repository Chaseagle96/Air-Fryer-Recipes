from pathlib import Path

from airfryer_rankings.dashboard import _dashboard_html


def test_dashboard_requires_authority_before_rendering_ranked_rows() -> None:
    html = _dashboard_html()
    assert "api/authority.json" in html
    assert "authority.authoritative!==true" in html
    assert "No ranked list is displayed" in html
    assert "Authoritative leaderboard unavailable" in html


def test_mobile_backfill_preserves_or_revokes_authority_explicitly() -> None:
    script = Path("scripts/backfill_mobile_corpus.py").read_text(encoding="utf-8")
    assert 'manifest["authority"] = authority' in script
    assert '"missing_authority_certificate"' in script
    assert '"authoritative": False' in script


def test_ios_live_client_revalidates_authority_for_cached_manifests() -> None:
    source = Path("ios/RecipeIntelligence/Networking.swift").read_text(encoding="utf-8")
    assert "case nonAuthoritativeFeed(String)" in source
    assert "let rankingGeneratedAt: String?" in source
    assert "try await assertAuthoritative(vertical: vertical, manifest: cached)" in source
    assert "guard authority.authoritative" in source
    assert "guard let rankingGeneratedAt = authority.rankingGeneratedAt" in source
    assert "rankingGeneratedAt == manifest.generatedAt" in source
