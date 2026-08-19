from pathlib import Path

import pytest
import yaml


@pytest.mark.parametrize(
    "path",
    [
        Path(".github/workflows/authority-invalidate.yml"),
        Path(".github/workflows/authoritative-refresh.yml"),
        Path(".github/workflows/authority-postcheck.yml"),
        Path(".github/workflows/hourly.yml"),
        Path(".github/workflows/slow-cooker.yml"),
        Path(".github/workflows/source-expansion.yml"),
        Path(".github/workflows/source-catalog-sync.yml"),
    ],
)
def test_authority_workflow_yaml_parses(path: Path) -> None:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    assert payload.get("name")
    assert payload.get("jobs")


@pytest.mark.parametrize(
    ("path", "certification_name", "authority_path"),
    [
        (
            Path(".github/workflows/hourly.yml"),
            "Certify Air Fryer authority before publication",
            "output/authority.json",
        ),
        (
            Path(".github/workflows/slow-cooker.yml"),
            "Certify Slow Cooker authority before publication",
            "verticals/slow_cooker/output/authority.json",
        ),
    ],
)
def test_production_ranking_workflow_certifies_before_commit(
    path: Path,
    certification_name: str,
    authority_path: str,
) -> None:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    steps = payload["jobs"]["refresh"]["steps"]
    names = [step.get("name") for step in steps]
    certify_index = names.index(certification_name)
    commit_index = next(index for index, name in enumerate(names) if name and name.startswith("Commit "))
    assert certify_index < commit_index
    commit_script = str(steps[commit_index].get("run") or "")
    assert authority_path in commit_script


@pytest.mark.parametrize(
    ("path", "job_name", "invalidate_name", "commit_prefix"),
    [
        (
            Path(".github/workflows/source-expansion.yml"),
            "source-expansion",
            "Invalidate ranked serving before source-network commit",
            "Commit source registries",
        ),
        (
            Path(".github/workflows/source-catalog-sync.yml"),
            "sync",
            "Invalidate ranked serving before catalog commit",
            "Commit synchronized URL catalogs",
        ),
    ],
)
def test_source_network_workflows_invalidate_serving_in_same_commit_transaction(
    path: Path,
    job_name: str,
    invalidate_name: str,
    commit_prefix: str,
) -> None:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    steps = payload["jobs"][job_name]["steps"]
    names = [step.get("name") for step in steps]
    invalidate_index = names.index(invalidate_name)
    commit_index = next(index for index, name in enumerate(names) if name and name.startswith(commit_prefix))
    assert invalidate_index < commit_index

    invalidate_script = str(steps[invalidate_index].get("run") or "")
    assert "scripts/ranking_authority.py invalidate" in invalidate_script
    assert "--vertical air_fryer" in invalidate_script
    assert "--vertical slow_cooker" in invalidate_script

    commit_script = str(steps[commit_index].get("run") or "")
    for required in (
        "output/authority.json",
        "docs/api/manifest.json",
        "docs/api/authority.json",
        "verticals/slow_cooker/output/authority.json",
        "verticals/slow_cooker/docs/api/manifest.json",
        "verticals/slow_cooker/docs/api/authority.json",
    ):
        assert required in commit_script


def test_slow_cooker_full_refresh_has_no_production_catalog_cap() -> None:
    payload = yaml.safe_load(Path(".github/workflows/slow-cooker.yml").read_text(encoding="utf-8"))
    steps = payload["jobs"]["refresh"]["steps"]
    refresh = next(step for step in steps if step.get("name") == "Refresh Slow Cooker rankings")
    script = str(refresh.get("run") or "")

    assert "max_urls=250" not in script
    assert "extra_args=(--hourly-limit 100)" in script
    assert "extra_args=(--max-urls 2 --hourly-limit 6)" in script
    assert '"${extra_args[@]}"' in script
