from __future__ import annotations

import json
import subprocess

import pytest

from airfryer_rankings.ops import run_vertical, validate_mobile_manifest


def _manifest() -> dict:
    return {
        "ranked_recipe_count": 2,
        "corpus_recipe_count": 3,
        "pages": [{"count": 2}],
        "corpus_pages": [{"count": 3}],
        "corpus_status_counts": {"discover": 2},
    }


def test_validate_mobile_manifest_accepts_consistent_counts(tmp_path) -> None:
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(_manifest()), encoding="utf-8")
    assert validate_mobile_manifest(path)["corpus_recipe_count"] == 3


def test_validate_mobile_manifest_rejects_inconsistent_counts(tmp_path) -> None:
    payload = _manifest()
    payload["corpus_pages"] = [{"count": 2}]
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="corpus page counts"):
        validate_mobile_manifest(path)


def test_validate_mobile_manifest_allows_unranked_corpus(tmp_path) -> None:
    payload = _manifest()
    payload["ranked_recipe_count"] = 0
    payload["pages"] = []
    payload["corpus_status_counts"] = {"discover": 3}
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert validate_mobile_manifest(path)["ranked_recipe_count"] == 0


def test_run_vertical_resolves_slow_cooker_paths(monkeypatch) -> None:
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert run_vertical("config/source_discovery.yaml", "slow-cooker", "hourly") == 0

    command, kwargs = calls[0]
    assert "--model-config" in command
    assert "config/verticals/slow_cooker/model.yaml" in command[command.index("--model-config") + 1]
    assert command[-2:] == ["--hourly-limit", "100"]
    assert kwargs["cwd"].name == "slow_cooker"
