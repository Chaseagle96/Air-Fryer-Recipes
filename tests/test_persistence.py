from __future__ import annotations

import json
from pathlib import Path

import pytest

import airfryer_rankings.persistence as persistence
from airfryer_rankings.persistence import (
    PersistenceCorruptionError,
    PersistenceError,
    PersistenceValidationError,
    PersistenceWriteError,
    atomic_write_json,
    load_json_object,
)
from airfryer_rankings.source_registry import empty_source_registry, load_source_registry, save_source_registry
from airfryer_rankings.storage import load_state, save_state


def test_missing_persisted_files_keep_first_run_defaults(tmp_path: Path) -> None:
    state = load_state(tmp_path / "missing-state.json")
    assert state["schema_version"] == 4
    assert state["recipes"] == {}
    assert state["migration"]["completed"] is True

    registry = load_source_registry(tmp_path / "missing-registry.json", "air_fryer")
    assert registry == empty_source_registry("air_fryer")


@pytest.mark.parametrize("contents", ["{", "", '{"recipes":'])
def test_malformed_state_fails_closed_without_replacing_file(tmp_path: Path, contents: str) -> None:
    path = tmp_path / "state.json"
    path.write_text(contents, encoding="utf-8")

    with pytest.raises(PersistenceCorruptionError):
        load_state(path)

    assert path.read_text(encoding="utf-8") == contents


@pytest.mark.parametrize(
    "payload, field",
    [
        ([], "object"),
        ({"recipes": []}, "recipes"),
        ({"url_catalog": []}, "url_catalog"),
        ({"rank_history": {}}, "rank_history"),
        ({"migration": []}, "migration"),
        ({"schema_version": "not-a-version"}, "schema_version"),
        ({"recipes": {"bad": []}}, "bad"),
        ({"url_catalog": {"https://example.com": []}}, "https://example.com"),
    ],
)
def test_structurally_invalid_state_is_rejected(tmp_path: Path, payload: object, field: str) -> None:
    path = tmp_path / "state.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(PersistenceValidationError, match=field):
        load_state(path)


@pytest.mark.parametrize(
    "payload, field",
    [
        ([], "object"),
        ({"candidates": []}, "candidates"),
        ({"manual_overrides": []}, "manual_overrides"),
        ({"audit": {}}, "audit"),
        ({"schema_version": "bad"}, "schema_version"),
        ({"source_gate_version": []}, "source_gate_version"),
        ({"vertical": 3}, "vertical"),
        ({"candidates": {"example.com": []}}, "example.com"),
        ({"manual_overrides": {"example.com": []}}, "example.com"),
        ({"audit": ["bad-event"]}, "audit event"),
    ],
)
def test_structurally_invalid_source_registry_is_rejected(
    tmp_path: Path,
    payload: object,
    field: str,
) -> None:
    path = tmp_path / "source_registry.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(PersistenceValidationError, match=field):
        load_source_registry(path, "air_fryer")


def test_minimal_valid_registry_remains_backward_compatible(tmp_path: Path) -> None:
    path = tmp_path / "source_registry.json"
    path.write_text('{"vertical": "air_fryer"}', encoding="utf-8")

    registry = load_source_registry(path, "air_fryer")

    assert registry["schema_version"] == 1
    assert registry["source_gate_version"] == 2
    assert registry["candidates"] == {}
    assert registry["manual_overrides"] == {}
    assert registry["audit"] == []


def test_state_save_is_atomic_when_replace_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "state.json"
    state = load_state(path)
    save_state(path, state)
    original = path.read_text(encoding="utf-8")
    state["rank_history"].append({"rank": 1})

    def fail_replace(source: str | Path, destination: str | Path) -> None:
        raise OSError(f"simulated replace failure: {source} -> {destination}")

    monkeypatch.setattr(persistence.os, "replace", fail_replace)

    with pytest.raises(PersistenceWriteError):
        save_state(path, state)

    assert path.read_text(encoding="utf-8") == original
    assert list(tmp_path.glob(".state.json.*.tmp")) == []


def test_state_save_is_atomic_when_serialization_fails(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    state = load_state(path)
    save_state(path, state)
    original = path.read_text(encoding="utf-8")
    state["unserializable"] = object()

    with pytest.raises(PersistenceWriteError):
        save_state(path, state)

    assert path.read_text(encoding="utf-8") == original


def test_source_registry_round_trip_uses_atomic_writer(tmp_path: Path) -> None:
    path = tmp_path / "source_registry.json"
    registry = empty_source_registry("air_fryer")
    registry["audit"].append({"timestamp": Path("2026-08-21")})

    save_source_registry(path, registry)
    reloaded = load_source_registry(path, "air_fryer")

    assert reloaded["schema_version"] == 1
    assert reloaded["source_gate_version"] == 2
    assert reloaded["audit"][0]["timestamp"] == "2026-08-21"


def test_load_json_object_surfaces_filesystem_read_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "state.json"
    path.write_text("{}", encoding="utf-8")
    original_read_text = Path.read_text

    def fail_read_text(self: Path, *args: object, **kwargs: object) -> str:
        if self == path:
            raise OSError("simulated read failure")
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", fail_read_text)

    with pytest.raises(PersistenceError, match="Unable to read"):
        load_json_object(path)


def test_atomic_write_json_replaces_complete_document(tmp_path: Path) -> None:
    path = tmp_path / "payload.json"
    path.write_text('{"old": true}\n', encoding="utf-8")

    atomic_write_json(path, {"new": True})

    assert json.loads(path.read_text(encoding="utf-8")) == {"new": True}
    assert list(tmp_path.glob(".payload.json.*.tmp")) == []
