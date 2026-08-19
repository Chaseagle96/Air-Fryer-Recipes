from pathlib import Path

from airfryer_rankings.dashboard import _dashboard_html


def test_dashboard_requires_matching_authority_before_rendering_ranked_rows() -> None:
    html = _dashboard_html()
    assert "api/authority.json" in html
    assert "authority.authoritative!==true" in html
    assert "authority.ranking_generated_at!==data.generated_at" in html
    assert "No ranked list is displayed" in html
    assert "Authoritative leaderboard unavailable" in html


def test_mobile_backfill_marks_uncertified_generation_refresh_required() -> None:
    script = Path("scripts/backfill_mobile_corpus.py").read_text(encoding="utf-8")
    assert 'manifest["authority"] = authority' in script
    assert 'manifest["ranked_serving_available"] = authority.get("authoritative") is True' in script
    assert '"ranking_generation_requires_certification"' in script
    assert "AUTHORITY_CONTRACT_VERSION" in script


def test_ios_live_client_revalidates_v2_authority_for_cached_manifests() -> None:
    source = Path("ios/RecipeIntelligence/Networking.swift").read_text(encoding="utf-8")
    assert "case nonAuthoritativeFeed(String)" in source
    assert "let authorityContractVersion: Int" in source
    assert "let rankingGeneratedAt: String?" in source
    assert "try await assertAuthoritative(vertical: vertical, manifest: cached)" in source
    assert "guard authority.authorityContractVersion >= 2" in source
    assert "guard authority.authoritative" in source
    assert "guard let rankingGeneratedAt = authority.rankingGeneratedAt" in source
    assert "rankingGeneratedAt == manifest.generatedAt" in source
