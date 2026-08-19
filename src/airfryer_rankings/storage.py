from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from .contracts import CLEAN_RECIPE_SCHEMA_VERSION, RAW_OBSERVATION_SCHEMA_VERSION
from .models import DEFAULT_STATE, RecipeRow, parse_dt

# The persisted state envelope remains v4 for backward compatibility. Individual
# clean recipe records and downstream contracts are independently versioned at V5.
STATE_SCHEMA_VERSION = 4
LEGACY_EVIDENCE_CONFIDENCE = 0.60
KNOWN_EVIDENCE_STATUSES = {"verified", "schema_only", "visible_only", "conflict", "legacy_unverified"}


def migrate_state(state: dict) -> dict:
    """Upgrade persisted records without silently preserving obsolete evidence or structural assumptions."""
    previous_version = int(state.get("schema_version") or 0)
    recipes = state.setdefault("recipes", {})
    catalog = state.setdefault("url_catalog", {})
    legacy_marked = 0
    structural_initialized = 0

    for recipe_id, recipe in recipes.items():
        status = str(recipe.get("evidence_status") or "").strip()
        confidence = recipe.get("evidence_confidence")
        is_legacy = (
            status not in KNOWN_EVIDENCE_STATUSES
            or not status
            or (confidence is not None and abs(float(confidence) - 0.85) < 1e-12 and status != "verified")
        )
        if is_legacy:
            recipe["evidence_status"] = "legacy_unverified"
            recipe["evidence_confidence"] = LEGACY_EVIDENCE_CONFIDENCE
            recipe["needs_evidence_backfill"] = True
            legacy_marked += 1
            canonical = recipe.get("canonical_url") or recipe.get("url")
            if canonical:
                entry = catalog.setdefault(
                    canonical,
                    {"url": canonical, "source": recipe.get("source", ""), "recipe_id": recipe_id},
                )
                entry["recipe_id"] = recipe_id
                entry["priority"] = "legacy_evidence_backfill"
        elif status != "legacy_unverified":
            recipe["needs_evidence_backfill"] = False

        for field, default in (
            ("dom_fingerprint", ""),
            ("schema_signature", ""),
            ("rating_evidence_signature", {}),
        ):
            if field not in recipe:
                recipe[field] = default
                structural_initialized += 1
        recipe["clean_schema_version"] = CLEAN_RECIPE_SCHEMA_VERSION

    pending = sum(1 for recipe in recipes.values() if recipe.get("needs_evidence_backfill"))
    state["schema_version"] = STATE_SCHEMA_VERSION
    state["migration"] = {
        "from_schema_version": previous_version,
        "to_schema_version": STATE_SCHEMA_VERSION,
        "clean_recipe_schema_version": CLEAN_RECIPE_SCHEMA_VERSION,
        "legacy_evidence_marked": legacy_marked,
        "legacy_evidence_pending": pending,
        "legacy_default_confidence": LEGACY_EVIDENCE_CONFIDENCE,
        "structural_fields_initialized": structural_initialized,
        "completed": pending == 0,
    }
    return state


def load_state(path: str | Path) -> dict:
    target = Path(path)
    if not target.exists():
        state = json.loads(json.dumps(DEFAULT_STATE))
        state["schema_version"] = STATE_SCHEMA_VERSION
        state["migration"] = {
            "from_schema_version": STATE_SCHEMA_VERSION,
            "to_schema_version": STATE_SCHEMA_VERSION,
            "clean_recipe_schema_version": CLEAN_RECIPE_SCHEMA_VERSION,
            "legacy_evidence_marked": 0,
            "legacy_evidence_pending": 0,
            "legacy_default_confidence": LEGACY_EVIDENCE_CONFIDENCE,
            "structural_fields_initialized": 0,
            "completed": True,
        }
        return state
    try:
        state = json.loads(target.read_text(encoding="utf-8"))
    except Exception:
        state = json.loads(json.dumps(DEFAULT_STATE))
    for key, default in DEFAULT_STATE.items():
        state.setdefault(key, json.loads(json.dumps(default)))
    return migrate_state(state)


def save_state(path: str | Path, state: dict) -> None:
    state["schema_version"] = STATE_SCHEMA_VERSION
    pending = sum(1 for recipe in state.get("recipes", {}).values() if recipe.get("needs_evidence_backfill"))
    migration = state.setdefault("migration", {})
    migration["legacy_evidence_pending"] = pending
    migration["completed"] = pending == 0
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")


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
        payload["needs_evidence_backfill"] = row.evidence_status == "legacy_unverified"
        payload["clean_schema_version"] = CLEAN_RECIPE_SCHEMA_VERSION
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
                "dom_fingerprint": row.dom_fingerprint,
                "schema_signature": row.schema_signature,
                "rating_evidence_signature": row.rating_evidence_signature,
                "canonical_url": row.canonical_url or row.url,
                "author": row.author,
                "ingredient_signature": row.ingredient_signature,
                "instruction_signature": row.instruction_signature,
                "instruction_simhash": row.instruction_simhash,
                "image_fingerprint": row.image_fingerprint,
                "image_perceptual_hash": row.image_perceptual_hash,
                "categories": list(row.categories),
                "rating_histogram": row.rating_histogram,
                "fetch_status": row.fetch_status,
                "schema_version": RAW_OBSERVATION_SCHEMA_VERSION,
            }
        )
    pending = sum(1 for recipe in recipes.values() if recipe.get("needs_evidence_backfill"))
    migration = state.setdefault("migration", {})
    migration["legacy_evidence_pending"] = pending
    migration["completed"] = pending == 0
    return observations


def write_run_records(base_dir: str | Path, records: Iterable[dict], run_at: str) -> str | None:
    records = list(records)
    if not records:
        return None
    timestamp = parse_dt(run_at) or datetime.now(timezone.utc)
    folder = Path(base_dir) / timestamp.strftime("%Y") / timestamp.strftime("%m") / timestamp.strftime("%d")
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{timestamp.strftime('%H%M%SZ')}.ndjson"
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
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
