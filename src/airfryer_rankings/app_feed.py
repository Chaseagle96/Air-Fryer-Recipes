from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .runtime import vertical_name, vertical_slug

APP_FEED_SCHEMA_VERSION = 1
DEFAULT_PAGE_SIZE = 100


def _categories(value: Any) -> list[str]:
    if isinstance(value, str):
        return [part.strip() for part in value.split("|") if part.strip()]
    if isinstance(value, (list, tuple, set)):
        return [str(part).strip() for part in value if str(part).strip()]
    return []


def build_app_recipe(row: dict) -> dict:
    """Project a ranked recipe into the public mobile-serving contract.

    Publisher instruction prose is intentionally not republished. The clean state
    may retain it for research/dedupe purposes, but mobile clients receive only a
    factual availability/count signal plus the canonical source URL.
    """
    ingredients = row.get("ingredients") or []
    if not isinstance(ingredients, (list, tuple)):
        ingredients = []
    return {
        "recipe_id": str(row.get("recipe_id") or ""),
        "vertical_id": vertical_slug(),
        "vertical_name": vertical_name(),
        "title": str(row.get("title") or ""),
        "source": str(row.get("source") or ""),
        "combined_sources": str(row.get("combined_sources") or row.get("source") or ""),
        "url": str(row.get("url") or ""),
        "canonical_url": str(row.get("canonical_url") or row.get("url") or ""),
        "image_url": str(row.get("image_url") or ""),
        "author": str(row.get("author") or ""),
        "categories": _categories(row.get("categories")),
        "ingredients": [str(value) for value in ingredients if str(value).strip()],
        "has_instructions": bool(row.get("has_instructions")),
        "instruction_count": int(row.get("instruction_count") or 0),
        "rank": int(row.get("rank") or 0),
        "rating": float(row.get("rating") or 0.0),
        "rating_count": int(row.get("rating_count") or 0),
        "hierarchical_score": float(row.get("hierarchical_score") or 0.0),
        "evidence_confidence": float(row.get("evidence_confidence") or 0.0),
        "evidence_grade": str(row.get("evidence_grade") or ""),
        "evidence_status": str(row.get("evidence_status") or ""),
        "rank_confidence": float(row.get("rank_confidence") or 0.0),
        "rank_range_low": row.get("rank_range_low"),
        "rank_range_high": row.get("rank_range_high"),
        "rank_provenance": str(row.get("rank_provenance") or ""),
    }


def write_app_feed(
    docs_dir: str | Path,
    generated_at: str,
    ranked: list[dict],
    source_count: int,
    *,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> str:
    if page_size <= 0:
        raise ValueError("page_size must be positive")

    root = Path(docs_dir) / "api"
    recipes_dir = root / "recipes"
    recipes_dir.mkdir(parents=True, exist_ok=True)
    for stale in recipes_dir.glob("*.json"):
        stale.unlink()

    projected = [build_app_recipe(row) for row in ranked]
    page_rows = [projected[index : index + page_size] for index in range(0, len(projected), page_size)]
    pages: list[dict] = []
    for index, rows in enumerate(page_rows, 1):
        filename = f"{index:04d}.json"
        payload = {
            "schema_version": APP_FEED_SCHEMA_VERSION,
            "generated_at": generated_at,
            "vertical_id": vertical_slug(),
            "vertical_name": vertical_name(),
            "page": index,
            "recipes": rows,
        }
        (recipes_dir / filename).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        pages.append({"index": index, "path": f"recipes/{filename}", "count": len(rows)})

    manifest = {
        "schema_version": APP_FEED_SCHEMA_VERSION,
        "generated_at": generated_at,
        "vertical": {
            "id": vertical_slug(),
            "name": vertical_name(),
            "source_count": int(source_count),
        },
        "recipe_count": len(projected),
        "page_size": page_size,
        "pages": pages,
        "content_policy": {
            "ingredients": "factual structured ingredient lines",
            "instructions": "publisher prose not republished; open canonical_url for full directions",
        },
    }
    manifest_path = root / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return str(manifest_path)
