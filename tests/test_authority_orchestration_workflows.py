from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_authority_invalidation_serializes_full_refresh_dispatch() -> None:
    workflow = (REPO_ROOT / ".github/workflows/authority-invalidate.yml").read_text(encoding="utf-8")

    assert "actions: write" in workflow
    assert "Dispatch full ranking refresh after invalidation" in workflow
    assert "github.event.workflow_run.name == 'Recipe Intelligence Source Catalog Sync'" in workflow
    assert "gh workflow run hourly.yml" in workflow
    assert "-f mode=daily" in workflow
    assert "gh workflow run slow-cooker.yml" in workflow

    commit_index = workflow.index("Commit authority invalidation when needed")
    dispatch_index = workflow.index("Dispatch full ranking refresh after invalidation")
    assert commit_index < dispatch_index


def test_authority_invalidation_stages_fail_closed_dashboards() -> None:
    workflow = (REPO_ROOT / ".github/workflows/authority-invalidate.yml").read_text(encoding="utf-8")

    assert "docs/index.html" in workflow
    assert "verticals/slow_cooker/docs/index.html" in workflow
    assert "Unexpected unstaged tracked changes remain after authority invalidation staging" in workflow


def test_source_expansion_does_not_dispatch_full_ranking_early() -> None:
    workflow = (REPO_ROOT / ".github/workflows/authority-invalidate.yml").read_text(encoding="utf-8")

    assert "github.event.workflow_run.name == 'Recipe Intelligence Source Expansion'" in workflow
    dispatch_block = workflow.split("- name: Dispatch full ranking refresh after invalidation", 1)[1]
    dispatch_condition = dispatch_block.split("env:", 1)[0]
    assert "Recipe Intelligence Source Catalog Sync" in dispatch_condition
    assert "Recipe Intelligence Source Expansion" not in dispatch_condition


def test_hourly_authority_defers_only_expected_full_refresh_requirement() -> None:
    air_fryer = (REPO_ROOT / ".github/workflows/hourly.yml").read_text(encoding="utf-8")
    slow_cooker = (REPO_ROOT / ".github/workflows/slow-cooker.yml").read_text(encoding="utf-8")
    expected = "new source/catalog/model generation requires a daily or deep refresh before certification"

    for workflow in (air_fryer, slow_cooker):
        assert "id: authority" in workflow
        assert expected in workflow
        assert "steps.mode.outputs.mode }}\" = \"hourly" in workflow
        assert "publishable=false" in workflow
        assert "exit \"$status\"" in workflow
        assert "steps.authority.outputs.publishable == 'true'" in workflow

    assert "publishable: ${{ steps.authority.outputs.publishable }}" in air_fryer
    assert "needs.refresh.outputs.publishable == 'true'" in air_fryer


def test_slow_cooker_manual_source_assertion_is_smoke_only() -> None:
    workflow = (REPO_ROOT / ".github/workflows/slow-cooker.yml").read_text(encoding="utf-8")

    assertion = 'expected_sources = {"skinnytaste.com", "budgetbytes.com", "wellplated.com"}'
    assert assertion in workflow
    prefix = workflow[: workflow.index(assertion)]
    assert 'if "${{ steps.mode.outputs.mode }}" == "smoke":' in prefix[-250:]


def test_authoritative_refresh_is_manual_fallback_only() -> None:
    workflow = (REPO_ROOT / ".github/workflows/authoritative-refresh.yml").read_text(encoding="utf-8")

    assert "workflow_dispatch:" in workflow
    assert "workflow_run:" not in workflow
    assert "\n  push:" not in workflow


def test_authority_self_heal_dispatches_only_stale_verticals() -> None:
    workflow = (REPO_ROOT / ".github/workflows/authority-self-heal.yml").read_text(encoding="utf-8")

    assert "Recipe Intelligence Authority Invalidation" in workflow
    assert "actions: write" in workflow
    assert "jq -e '.authoritative == true and .status == \"authoritative\"'" in workflow
    assert "gh workflow run \"$workflow\"" in workflow
    assert "-f mode=daily" in workflow
    assert "hourly.yml 'Air Fryer'" in workflow
    assert "slow-cooker.yml 'Slow Cooker'" in workflow


def test_authority_self_heal_avoids_duplicate_and_retry_loops() -> None:
    workflow = (REPO_ROOT / ".github/workflows/authority-self-heal.yml").read_text(encoding="utf-8")

    assert "gh run list" in workflow
    assert '.status == "queued"' in workflow
    assert '.status == "in_progress"' in workflow
    assert "Recipe Intelligence — Slow Cooker" not in workflow
    assert "workflows:\n      - Recipe Intelligence Authority Invalidation" in workflow
