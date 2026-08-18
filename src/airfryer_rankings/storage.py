from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from .models import DEFAULT_STATE, RecipeRow, parse_dt
def load_state(path: str | Path) -> dict:
    p = Path(path)
    if not p.exists():
        return json.loads(json.dumps(DEFAULT_STATE))
    try:
        state = json.loads(p.read_text())
    except Exception:
        return json.loads(json.dumps(DEFAULT_STATE))
    for key, default in DEFAULT_STATE.items():
        state.setdefault(key, json.loads(json.dumps(default)))
    state["schema_version"] = 3
    return state


def save_state(path: str | Path, state: dict) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")


def merge_observations(state: dict, rows: Iterable[RecipeRow], run_at: str) -> list[dict]:
    recipes = state.setdefault("recipes", {})
    observations: list[dict] = []
    for row in rows:
        existing = recipes.get(row.recipe_id, {})
        payload = asdict(row)
        payload["first_seen_at"] = existing.get("first_seen_at", run_at)
        payload["last_seen_at"] = run_at
        payload["last_run_at"] = run_at
        payload["previous_rating"] = existing.get("normalized_rating")
        payload["previous_rating_count"] = existing.get("rating_count")
        payload["previous_seen_at"] = existing.get("last_seen_at")
        payload["last_rank"] = existing.get("last_rank")
        recipes[row.recipe_id] = payload
        observations.append(
            {
                "recipe_id": row.recipe_id,
                "timestamp": run_at,
                "source": row.source,
                "url": row.canonical_url or row.url,
                "title": row.title,
                "rating": row.normalized_rating,
                "rating_count": row.rating_count,
                "evidence_confidence": row.evidence_confidence,
                "evidence_status": row.evidence_status,
                "extraction_method": row.extraction_method,
                "page_hash": row.page_hash,
                "canonical_url": row.canonical_url or row.url,
                "author": row.author,
                "ingredient_signature": row.ingredient_signature,
                "instruction_signature": row.instruction_signature,
                "image_fingerprint": row.image_fingerprint,
                "categories": list(row.categories),
                "rating_histogram": row.rating_histogram,
                "fetch_status": row.fetch_status,
                "schema_version": 3,
            }
        )
    return observations


def write_run_records(base_dir: str | Path, records: Iterable[dict], run_at: str) -> str | None:
    records = list(records)
    if not records:
        return None
    dt = parse_dt(run_at) or datetime.now(timezone.utc)
    folder = Path(base_dir) / dt.strftime("%Y") / dt.strftime("%m") / dt.strftime("%d")
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{dt.strftime('%H%M%SZ')}.ndjson"
    with path.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, sort_keys=True) + "\n")
    return str(path)


def read_recent_records(base_dir: str | Path, limit: int = 5000) -> list[dict]:
    root = Path(base_dir)
    if not root.exists():
        return []
    files = sorted(root.rglob("*.ndjson"), reverse=True)
    output: list[dict] = []
    for path in files:
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except Exception:
            continue
        for line in reversed(lines):
            try:
                output.append(json.loads(line))
            except Exception:
                continue
            if len(output) >= limit:
                return list(reversed(output))
    return list(reversed(output))
