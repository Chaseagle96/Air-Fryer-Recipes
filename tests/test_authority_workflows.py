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
