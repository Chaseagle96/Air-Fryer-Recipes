from __future__ import annotations

import importlib.util
from pathlib import Path

from airfryer_rankings.authority import AUTHORITY_CONTRACT_VERSION


def _load_backfill_module():
    path = Path("scripts/backfill_mobile_corpus.py")
    spec = importlib.util.spec_from_file_location("backfill_mobile_corpus_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_mobile_backfill_defaults_missing_authority_to_refresh_required() -> None:
    module = _load_backfill_module()
    authority = module._authority({})
    assert authority == {
        "authority_contract_version": AUTHORITY_CONTRACT_VERSION,
        "authoritative": False,
        "status": "refresh_required",
        "reason": "missing_or_obsolete_authority_certificate",
    }


def test_mobile_backfill_preserves_current_authority_certificate() -> None:
    module = _load_backfill_module()
    certificate = {
        "authority_contract_version": AUTHORITY_CONTRACT_VERSION,
        "authoritative": False,
        "status": "refresh_required",
        "reason": "source_or_catalog_generation_advanced",
    }
    assert module._authority({"authority": certificate}) == certificate


def test_mobile_backfill_cannot_resurrect_ranked_manifest_pointers() -> None:
    source = Path("scripts/backfill_mobile_corpus.py").read_text(encoding="utf-8")
    assert 'serving_available = authority.get("authoritative") is True' in source
    assert 'manifest["ranked_serving_available"] = serving_available' in source
    assert 'manifest["ranked_recipe_count"] = 0' in source
    assert 'manifest["pages"] = []' in source


def test_ios_live_client_revalidates_authority_even_for_cached_manifest() -> None:
    source = Path("ios/RecipeIntelligence/Networking.swift").read_text(encoding="utf-8")
    assert "case nonAuthoritativeFeed(String)" in source
    assert "private static let authorityContractVersion = 2" in source
    assert "try await assertAuthoritative(vertical: vertical, manifest: cached)" in source
    assert "guard authority.authoritative" in source
    assert "guard let rankingGeneratedAt = authority.rankingGeneratedAt" in source
    assert "rankingGeneratedAt == manifest.generatedAt" in source
