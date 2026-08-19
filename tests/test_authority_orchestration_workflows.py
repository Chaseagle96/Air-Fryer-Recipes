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


def test_source_expansion_does_not_dispatch_full_ranking_early() -> None:
    workflow = (REPO_ROOT / ".github/workflows/authority-invalidate.yml").read_text(encoding="utf-8")

    assert "github.event.workflow_run.name == 'Recipe Intelligence Source Expansion'" in workflow
    dispatch_block = workflow.split("- name: Dispatch full ranking refresh after invalidation", 1)[1]
    dispatch_condition = dispatch_block.split("env:", 1)[0]
    assert "Recipe Intelligence Source Catalog Sync" in dispatch_condition
    assert "Recipe Intelligence Source Expansion" not in dispatch_condition


def test_authoritative_refresh_is_manual_fallback_only() -> None:
    workflow = (REPO_ROOT / ".github/workflows/authoritative-refresh.yml").read_text(encoding="utf-8")

    assert "workflow_dispatch:" in workflow
    assert "workflow_run:" not in workflow
    assert "\n  push:" not in workflow
