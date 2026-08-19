from __future__ import annotations

import json
from pathlib import Path

from airfryer_rankings.core import SourceConfig, extract_recipe_from_html

FIXTURE_ROOT = Path("tests/fixtures/real_pages")


def test_reviewed_real_page_fixtures_preserve_extraction_contracts():
    manifest = json.loads((FIXTURE_ROOT / "manifest.json").read_text(encoding="utf-8"))
    assert len(manifest["fixtures"]) >= 7
    for fixture in manifest["fixtures"]:
        html = (FIXTURE_ROOT / fixture["fixture"]).read_text(encoding="utf-8")
        row, metadata = extract_recipe_from_html(
            html,
            fixture["url"],
            fixture["source"],
            SourceConfig(fixture["source"]),
        )
        assert row is not None, fixture["fixture"]
        assert row.evidence_status == fixture["expected_status"], fixture["fixture"]
        assert abs(row.normalized_rating - float(fixture["expected_rating"])) <= 0.011
        assert row.rating_count == int(fixture["expected_rating_count"])
        assert row.dom_fingerprint
        assert row.schema_signature
        assert metadata["dom_fingerprint"] == row.dom_fingerprint
        assert metadata["schema_signature"] == row.schema_signature


def test_structural_fingerprints_are_stable_for_checked_in_fixtures():
    manifest = json.loads((FIXTURE_ROOT / "manifest.json").read_text(encoding="utf-8"))
    for fixture in manifest["fixtures"]:
        html = (FIXTURE_ROOT / fixture["fixture"]).read_text(encoding="utf-8")
        first, first_meta = extract_recipe_from_html(html, fixture["url"], fixture["source"])
        second, second_meta = extract_recipe_from_html(html, fixture["url"], fixture["source"])
        assert first is not None and second is not None
        assert first_meta["dom_fingerprint"] == second_meta["dom_fingerprint"]
        assert first_meta["schema_signature"] == second_meta["schema_signature"]
