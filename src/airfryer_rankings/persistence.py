from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Callable

JsonDefault = Callable[[Any], Any]


class PersistenceError(RuntimeError):
    """Base error for persisted JSON read/write failures."""


class PersistenceCorruptionError(PersistenceError):
    """Raised when an existing persisted JSON file cannot be decoded."""


class PersistenceValidationError(PersistenceError):
    """Raised when persisted JSON has an invalid structural shape."""


class PersistenceWriteError(PersistenceError):
    """Raised when a persisted JSON replacement cannot be completed safely."""


def load_json_object(path: str | Path) -> dict:
    """Load an existing JSON object without converting corruption into empty state."""
    target = Path(path)
    try:
        raw = target.read_text(encoding="utf-8")
    except OSError as exc:
        raise PersistenceError(f"Unable to read persisted JSON: {target}") from exc

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise PersistenceCorruptionError(
            f"Malformed JSON in {target} at line {exc.lineno}, column {exc.colno}"
        ) from exc

    if not isinstance(payload, dict):
        raise PersistenceValidationError(f"Persisted JSON must be an object: {target}")
    return payload


def atomic_write_json(
    path: str | Path,
    payload: object,
    *,
    default: JsonDefault | None = None,
) -> None:
    """Durably stage JSON beside its target, then atomically replace the target."""
    target = Path(path)
    temporary: Path | None = None
    try:
        serialized = json.dumps(payload, indent=2, sort_keys=True, default=default) + "\n"
        target.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=target.parent,
            prefix=f".{target.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(serialized)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
        temporary = None
    except Exception as exc:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
        raise PersistenceWriteError(f"Unable to atomically write persisted JSON: {target}") from exc
