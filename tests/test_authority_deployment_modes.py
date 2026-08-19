from pathlib import Path

import pytest
import yaml


@pytest.mark.parametrize(
    ("path", "resolve_step_name"),
    [
        (Path(".github/workflows/hourly.yml"), "Resolve refresh mode"),
        (Path(".github/workflows/slow-cooker.yml"), "Resolve Slow Cooker refresh mode"),
    ],
)
def test_push_deployments_resolve_to_daily_full_refresh(path: Path, resolve_step_name: str) -> None:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    steps = payload["jobs"]["refresh"]["steps"]
    resolve = next(step for step in steps if step.get("name") == resolve_step_name)
    script = str(resolve.get("run") or "")
    assert 'github.event_name }}" = "push"' in script
    assert "mode=daily" in script
