from __future__ import annotations

import json
from pathlib import Path

import pytest

from airfryer_rankings.authority import AuthorityError, invalidate_authority, publish_authority


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _fixture(tmp_path: Path) -> dict[str, Path]:
    sources = tmp_path / "sources.yaml"
    sources.write_text("sources:\n  - domain: trusted.example\n", encoding="utf-8")
    state = tmp_path / "state.json"
    _write(
        state,
        {
            "recipes": {},
            "url_catalog": {
                "https://trusted.example/air-fryer-chicken": {
                    "url": "https://trusted.example/air-fryer-chicken",
                    "source": "trusted.example",
                }
            },
            "effective_source_domains": ["trusted.example"],
            "source_history": [],
            "schema_version": 5,
        },
    )
    registry = tmp_path / "registry.json"
    _write(
        registry,
        {
            "schema_version": 1,
            "source_gate_version": 2,
            "vertical": "air_fryer",
            "candidates": {},
            "manual_overrides": {},
            "audit": [],
        },
    )
    metrics = tmp_path / "source_expansion.json"
    _write(
        metrics,
        {
            "generated_at": "2026-08-19T10:00:00+00:00",
            "catalog_sync_generated_at": "2026-08-19T10:05:00+00:00",
            "source_gate_version": 2,
            "catalog_url_count": 1,
        },
    )
    summary = tmp_path / "summary.json"
    _write(
        summary,
        {
            "generated_at": "2026-08-19T10:10:00+00:00",
            "mode": "daily",
            "configured_sources": 1,
            "catalog_urls": 1,
            "targets_this_run": 1,
            "ranked_recipes": 1,
            "model_version": 5,
            "model_semver": "5.2.0",
        },
    )
    leaderboard = tmp_path / "leaderboard.csv"
    leaderboard.write_text("rank,title\n1,Air Fryer Chicken\n", encoding="utf-8")
    authority = tmp_path / "authority.json"
    public_authority = tmp_path / "docs" / "api" / "authority.json"
    manifest = tmp_path / "docs" / "api" / "manifest.json"
    _write(manifest, {"ranked_recipe_count": 1})
    return {
        "sources": sources,
        "state": state,
        "registry": registry,
        "metrics": metrics,
        "summary": summary,
        "leaderboard": leaderboard,
        "authority": authority,
        "public_authority": public_authority,
        "manifest": manifest,
    }


def _publish(paths: dict[str, Path]) -> dict:
    return publish_authority(
        vertical="air_fryer",
        sources_path=paths["sources"],
        state_path=paths["state"],
        registry_path=paths["registry"],
        metrics_path=paths["metrics"],
        summary_path=paths["summary"],
        leaderboard_path=paths["leaderboard"],
        authority_path=paths["authority"],
        public_authority_path=paths["public_authority"],
        manifest_path=paths["manifest"],
    )


def test_publish_authority_certifies_matching_generation(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)
    payload = _publish(paths)

    assert payload["authoritative"] is True
    assert payload["authority_contract_version"] == 2
    assert payload["effective_source_count"] == 1
    assert payload["effective_catalog_url_count"] == 1
    assert payload["ranking_mode"] == "daily"
    assert payload["full_catalog_baseline"] is True
    assert len(payload["generation_fingerprint_sha256"]) == 64
    assert json.loads(paths["summary"].read_text(encoding="utf-8"))["authority"]["authoritative"] is True
    assert json.loads(paths["manifest"].read_text(encoding="utf-8"))["authority"]["authoritative"] is True


def test_publish_authority_rejects_ranking_older_than_catalog_sync(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)
    summary = json.loads(paths["summary"].read_text(encoding="utf-8"))
    summary["generated_at"] = "2026-08-19T10:04:00+00:00"
    _write(paths["summary"], summary)

    with pytest.raises(AuthorityError, match="predates"):
        _publish(paths)


def test_publish_authority_rejects_catalog_count_drift(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)
    state = json.loads(paths["state"].read_text(encoding="utf-8"))
    state["url_catalog"]["https://trusted.example/air-fryer-potatoes"] = {
        "url": "https://trusted.example/air-fryer-potatoes",
        "source": "trusted.example",
    }
    _write(paths["state"], state)

    with pytest.raises(AuthorityError, match="catalog mismatch"):
        _publish(paths)


def test_publish_authority_rejects_ranking_scope_drift(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)
    state = json.loads(paths["state"].read_text(encoding="utf-8"))
    state["effective_source_domains"] = ["retired.example"]
    _write(paths["state"], state)

    with pytest.raises(AuthorityError, match="ranking source scope"):
        _publish(paths)


@pytest.mark.parametrize("mode", ["hourly", "backfill"])
def test_new_generation_requires_true_full_refresh_before_certification(tmp_path: Path, mode: str) -> None:
    paths = _fixture(tmp_path)
    summary = json.loads(paths["summary"].read_text(encoding="utf-8"))
    summary["mode"] = mode
    _write(paths["summary"], summary)

    with pytest.raises(AuthorityError, match="daily or deep"):
        _publish(paths)


def test_new_generation_rejects_partial_daily_catalog_coverage(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)
    state = json.loads(paths["state"].read_text(encoding="utf-8"))
    state["url_catalog"]["https://trusted.example/air-fryer-potatoes"] = {
        "url": "https://trusted.example/air-fryer-potatoes",
        "source": "trusted.example",
    }
    _write(paths["state"], state)
    metrics = json.loads(paths["metrics"].read_text(encoding="utf-8"))
    metrics["catalog_url_count"] = 2
    _write(paths["metrics"], metrics)
    summary = json.loads(paths["summary"].read_text(encoding="utf-8"))
    summary["catalog_urls"] = 2
    summary["targets_this_run"] = 1
    _write(paths["summary"], summary)

    with pytest.raises(AuthorityError, match="complete effective catalog"):
        _publish(paths)


def test_non_effective_catalog_rows_do_not_expand_authority_universe(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)
    state = json.loads(paths["state"].read_text(encoding="utf-8"))
    state["url_catalog"]["https://suspended.example/air-fryer-old"] = {
        "url": "https://suspended.example/air-fryer-old",
        "source": "suspended.example",
    }
    _write(paths["state"], state)
    metrics = json.loads(paths["metrics"].read_text(encoding="utf-8"))
    metrics["catalog_url_count"] = 2
    _write(paths["metrics"], metrics)
    summary = json.loads(paths["summary"].read_text(encoding="utf-8"))
    summary["catalog_urls"] = 2
    _write(paths["summary"], summary)

    payload = _publish(paths)
    assert payload["effective_catalog_url_count"] == 1
    assert payload["raw_catalog_url_count"] == 2


def test_hourly_refresh_inherits_authority_when_inputs_are_unchanged(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)
    baseline = _publish(paths)
    summary = json.loads(paths["summary"].read_text(encoding="utf-8"))
    summary.pop("authority", None)
    summary["generated_at"] = "2026-08-19T11:10:00+00:00"
    summary["mode"] = "hourly"
    summary["targets_this_run"] = 0
    _write(paths["summary"], summary)
    paths["leaderboard"].write_text("rank,title\n1,Air Fryer Potatoes\n", encoding="utf-8")

    hourly = _publish(paths)
    assert hourly["authoritative"] is True
    assert hourly["full_catalog_baseline"] is False
    assert hourly["input_fingerprint_sha256"] == baseline["input_fingerprint_sha256"]
    assert hourly["leaderboard_fingerprint_sha256"] != baseline["leaderboard_fingerprint_sha256"]


def test_invalidation_is_fail_closed_but_ignores_late_race(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)
    first = invalidate_authority(
        vertical="air_fryer",
        metrics_path=paths["metrics"],
        summary_path=paths["summary"],
        authority_path=paths["authority"],
        public_authority_path=paths["public_authority"],
        manifest_path=paths["manifest"],
        invalidated_at="2026-08-19T10:06:00+00:00",
    )
    assert first["authoritative"] is False

    _publish(paths)
    late = invalidate_authority(
        vertical="air_fryer",
        metrics_path=paths["metrics"],
        summary_path=paths["summary"],
        authority_path=paths["authority"],
        invalidated_at="2026-08-19T10:11:00+00:00",
    )
    assert late["authoritative"] is True
