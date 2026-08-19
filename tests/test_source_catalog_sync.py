from __future__ import annotations

import json
from pathlib import Path

import yaml

from airfryer_rankings.models import SourceConfig
from airfryer_rankings.source_catalog_sync import sync_promoted_source_catalogs
from airfryer_rankings.source_registry import (
    PROMOTED,
    empty_source_registry,
    record_candidate_discovery,
    save_source_registry,
    transition_source,
)


def test_promoted_source_is_seeded_into_persistent_catalog(tmp_path: Path, monkeypatch) -> None:
    import airfryer_rankings.source_catalog_sync as sync

    sources_path = tmp_path / "sources.yaml"
    state_path = tmp_path / "state.json"
    registry_path = tmp_path / "registry.json"
    output_dir = tmp_path / "output"
    aggregate_path = output_dir / "source_expansion_all.json"
    output_dir.mkdir()

    sources_path.write_text("sources:\n  - domain: pinned.example\n", encoding="utf-8")
    state_path.write_text(
        json.dumps({"recipes": {}, "url_catalog": {}, "source_history": [], "schema_version": 4}),
        encoding="utf-8",
    )
    registry = empty_source_registry("air_fryer")
    record, _ = record_candidate_discovery(
        registry,
        domain="quality.example",
        provider="unit",
        query="air fryer recipes",
        discovery_url="https://quality.example/air-fryer/",
        timestamp="2026-08-19T00:00:00+00:00",
    )
    assert record is not None
    record["crawl_config"] = {
        "include_pattern": r"air[- ]?fry(?:er|ing)",
        "discovery_urls": ["https://quality.example/air-fryer/"],
    }
    transition_source(registry, "quality.example", PROMOTED, "test promotion")
    save_source_registry(registry_path, registry)

    (output_dir / "source_expansion.json").write_text(
        json.dumps({"vertical": "air_fryer", "catalog_url_count": 0}), encoding="utf-8"
    )
    aggregate_path.write_text(
        json.dumps({"mode": "deep", "verticals": {"air_fryer": {"catalog_url_count": 0}}}), encoding="utf-8"
    )
    config = {
        "aggregate_output_path": str(aggregate_path),
        "budgets": {"deep": {"promotion_catalog_discovery_cap": 50}},
        "verticals": {
            "air_fryer": {
                "base_sources_path": str(sources_path),
                "state_path": str(state_path),
                "registry_path": str(registry_path),
                "output_dir": str(output_dir),
            }
        },
    }
    config_path = tmp_path / "source_discovery.yaml"
    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")

    def fake_discover(cfg: SourceConfig, state: dict, mode: str, run_at: str, global_max_urls: int | None = None):
        assert cfg.domain == "quality.example"
        assert cfg.origin == "discovered"
        assert mode == "deep"
        assert global_max_urls == 50
        for index in range(5):
            url = f"https://quality.example/air-fryer-recipe-{index}"
            state.setdefault("url_catalog", {})[url] = {"url": url, "source": cfg.domain}
        return {"source": cfg.domain, "status": "ok", "new_urls": 5, "discovered_urls": 5}

    monkeypatch.setattr(sync, "discover_source_urls", fake_discover)
    result = sync_promoted_source_catalogs(
        config_path,
        mode="auto",
        run_at="2026-08-19T01:00:00+00:00",
    )

    persisted = json.loads(state_path.read_text(encoding="utf-8"))
    assert len(persisted["url_catalog"]) == 5
    vertical = result["verticals"]["air_fryer"]
    assert vertical["manual_source_count"] == 1
    assert vertical["auto_source_count"] == 1
    assert vertical["effective_source_count"] == 2
    assert vertical["catalog_urls_added"] == 5

    metrics = json.loads((output_dir / "source_expansion.json").read_text(encoding="utf-8"))
    assert metrics["catalog_url_count"] == 5
    assert metrics["catalog_urls_added_after_promotion"] == 5
    aggregate = json.loads(aggregate_path.read_text(encoding="utf-8"))
    assert aggregate["verticals"]["air_fryer"]["catalog_url_count"] == 5
