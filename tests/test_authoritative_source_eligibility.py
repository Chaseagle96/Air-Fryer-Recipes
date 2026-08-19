from __future__ import annotations

import json
from pathlib import Path

import pytest

from airfryer_rankings.authority import AuthorityError, publish_authority
from airfryer_rankings.core import RecipeRow, bayesian_rank, merge_observations


def _recipe(
    recipe_id: str,
    source: str,
    rating: float,
    count: int,
    *,
    title: str | None = None,
    url: str | None = None,
) -> RecipeRow:
    recipe_url = url or f"https://{source}/{recipe_id}"
    return RecipeRow(
        recipe_id=recipe_id,
        title=title or f"Air Fryer {recipe_id}",
        source=source,
        url=recipe_url,
        rating=rating,
        rating_count=count,
        best_rating=5.0,
        normalized_rating=rating,
        retrieved_at="2026-08-19T12:00:00+00:00",
        canonical_url=recipe_url,
        evidence_confidence=1.0,
        evidence_status="verified",
    )


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _authority_fixture(tmp_path: Path) -> dict[str, Path]:
    sources = tmp_path / "sources.yaml"
    sources.write_text("sources:\n  - domain: trusted.example\n", encoding="utf-8")

    state = tmp_path / "state.json"
    _write(
        state,
        {
            "recipes": {},
            "url_catalog": {
                "https://trusted.example/a": {"url": "https://trusted.example/a", "source": "trusted.example"},
                "https://trusted.example/b": {"url": "https://trusted.example/b", "source": "trusted.example"},
            },
            "source_history": [],
            "rank_history": [],
            "anomaly_history": [],
            "migration": {},
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
            "catalog_url_count": 2,
        },
    )

    summary = tmp_path / "summary.json"
    _write(
        summary,
        {
            "generated_at": "2026-08-19T10:10:00+00:00",
            "configured_sources": 1,
            "catalog_urls": 2,
            "eligible_catalog_urls": 2,
            "targets_this_run": 2,
            "ranked_recipes": 1,
            "mode": "daily",
            "model_version": 5,
            "model_semver": "5.2.0",
        },
    )

    leaderboard = tmp_path / "leaderboard.csv"
    leaderboard.write_text("rank,title,source,url\n1,Air Fryer A,trusted.example,https://trusted.example/a\n", encoding="utf-8")
    authority = tmp_path / "authority.json"
    return {
        "sources": sources,
        "state": state,
        "registry": registry,
        "metrics": metrics,
        "summary": summary,
        "leaderboard": leaderboard,
        "authority": authority,
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
    )


def test_bayesian_rank_immediately_evicts_non_effective_sources() -> None:
    state = {
        "recipes": {},
        "url_catalog": {},
        "rank_history": [],
        "source_history": [],
        "anomaly_history": [],
        "migration": {},
        "schema_version": 5,
    }
    merge_observations(
        state,
        [
            _recipe("suspended-winner", "suspended.example", 5.0, 100000),
            _recipe("active-runner-up", "active.example", 4.8, 1000),
        ],
        "2026-08-19T12:00:00+00:00",
    )

    unrestricted, _ = bayesian_rank(state, stale_days=10000)
    restricted, method = bayesian_rank(
        state,
        stale_days=10000,
        allowed_sources={"active.example"},
    )

    assert {row["source"] for row in unrestricted} == {"active.example", "suspended.example"}
    assert [row["source"] for row in restricted] == ["active.example"]
    assert method["candidate_count"] == 1
    assert "suspended.example" not in method["source_adjustments"]


def test_slow_cooker_ranking_evicts_retained_cross_vertical_recipe() -> None:
    state = {
        "recipes": {},
        "url_catalog": {},
        "rank_history": [],
        "source_history": [],
        "anomaly_history": [],
        "migration": {},
        "schema_version": 5,
    }
    merge_observations(
        state,
        [
            _recipe(
                "birria",
                "budgetbytes.com",
                5.0,
                50000,
                title="Birria Tacos",
                url="https://www.budgetbytes.com/birria-tacos/",
            ),
            _recipe(
                "slow-lemon",
                "skinnytaste.com",
                4.9,
                1000,
                title="Slow Cooker Lemon Feta Drumsticks",
                url="https://www.skinnytaste.com/slow-cooker-lemon-feta-chicken/",
            ),
        ],
        "2026-08-19T12:00:00+00:00",
    )

    ranked, method = bayesian_rank(
        state,
        stale_days=10000,
        model_config_path="config/verticals/slow_cooker/model.yaml",
        allowed_sources={"budgetbytes.com", "skinnytaste.com"},
    )

    assert [row["recipe_id"] for row in ranked] == ["slow-lemon"]
    assert method["candidate_count"] == 1


def test_new_authority_baseline_requires_entire_effective_catalog(tmp_path: Path) -> None:
    paths = _authority_fixture(tmp_path)
    summary = json.loads(paths["summary"].read_text(encoding="utf-8"))
    summary["targets_this_run"] = 1
    _write(paths["summary"], summary)

    with pytest.raises(AuthorityError, match="entire effective catalog"):
        _publish(paths)


def test_backfill_cannot_establish_new_authority_baseline(tmp_path: Path) -> None:
    paths = _authority_fixture(tmp_path)
    summary = json.loads(paths["summary"].read_text(encoding="utf-8"))
    summary["mode"] = "backfill"
    _write(paths["summary"], summary)

    with pytest.raises(AuthorityError, match="daily or deep"):
        _publish(paths)


def test_authority_rejects_leaderboard_source_outside_effective_registry(tmp_path: Path) -> None:
    paths = _authority_fixture(tmp_path)
    paths["leaderboard"].write_text(
        "rank,title,source,url\n1,Stale Recipe,suspended.example,https://suspended.example/stale\n",
        encoding="utf-8",
    )

    with pytest.raises(AuthorityError, match="non-effective sources"):
        _publish(paths)


def test_authority_rejects_recipe_outside_strict_vertical_policy(tmp_path: Path) -> None:
    paths = _authority_fixture(tmp_path)
    paths["sources"].write_text(
        "defaults:\n"
        "  include_pattern: '(?:slow[-_ ]?cook(?:er|ing|ed)|crock[-_ ]?pot)'\n"
        "  allow_unmatched_discovery_links: false\n"
        "sources:\n"
        "  - domain: trusted.example\n",
        encoding="utf-8",
    )
    paths["leaderboard"].write_text(
        "rank,title,source,url\n1,Birria Tacos,trusted.example,https://trusted.example/birria-tacos/\n",
        encoding="utf-8",
    )

    with pytest.raises(AuthorityError, match="strict vertical policy"):
        _publish(paths)


def test_incremental_run_can_inherit_unchanged_certified_input_generation(tmp_path: Path) -> None:
    paths = _authority_fixture(tmp_path)
    baseline = _publish(paths)
    assert baseline["authoritative"] is True

    summary = json.loads(paths["summary"].read_text(encoding="utf-8"))
    summary["generated_at"] = "2026-08-19T10:20:00+00:00"
    summary["mode"] = "hourly"
    summary["targets_this_run"] = 1
    _write(paths["summary"], summary)

    incremental = _publish(paths)
    assert incremental["authoritative"] is True
    assert incremental["ranking_mode"] == "hourly"
    assert incremental["eligible_catalog_url_count"] == 2


def test_slow_cooker_full_refresh_is_not_capped_to_250_urls() -> None:
    workflow = Path(".github/workflows/slow-cooker.yml").read_text(encoding="utf-8")
    assert "max_urls=250" not in workflow
    assert "max_url_args=(--max-urls 2)" in workflow
    assert "cmd+=(\"${max_url_args[@]}\")" in workflow
