from pathlib import Path

import pytest
import yaml


@pytest.mark.parametrize(
    "path",
    [
        Path(".github/workflows/authority-invalidate.yml"),
        Path(".github/workflows/authoritative-refresh.yml"),
        Path(".github/workflows/authority-postcheck.yml"),
    ],
)
def test_authority_workflow_yaml_parses(path: Path) -> None:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    assert payload.get("name")
    assert payload.get("jobs")
