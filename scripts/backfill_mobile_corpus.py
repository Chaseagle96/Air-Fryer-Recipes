from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from airfryer_rankings.app_feed import write_app_feed
from airfryer_rankings.authority import AUTHORITY_CONTRACT_VERSION
from airfryer_rankings.core import load_sources
from airfryer_rankings.models import now_iso

INT_FIELDS = {"rank", "rating_count", "rank_range_low", "rank_range_high", "instruction_count"}
FLOAT_FIELDS = {
    "rating",
    "hierarchical_score",
    "evidence_confidence",
    "rank_confidence",
    "duplicate_confidence",
}
NULLABLE_INT_FIELDS = {"rank_range_low", "rank_range_high"}


def _coerce_ranked_row(row: dict[str, str]) -> dict:
    output: dict = dict(row)
    for key in INT_FIELDS:
        value = row.get(key, "")
        if key in NULLABLE_INT_FIELDS and not str(value).strip():
            output[key] = None
        else:
            try:
                output[key] = int(float(value)) if str(value).strip() else 0
            except (TypeError, ValueError):
                output[key] = None if key in NULLABLE_INT_FIELDS else 0
    for key in FLOAT_FIELDS:
        value = row.get(key, "")
        try:
            output[key] = float(value) if str(value).strip() else 0.0
        except (TypeError, ValueError):
            output[key] = 0.0
    return output


def _read_ranked(path: Path, recipes: dict[str, dict]) -> list[dict]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = []
        for raw in csv.DictReader(handle):
            row = _coerce_ranked_row(raw)
            recipe_id = str(row.get("recipe_id") or "")
            clean = recipes.get(recipe_id, {})
            # Clean state owns factual recipe content; leaderboard owns scoring.
            merged = dict(clean)
            merged.update(row)
            if clean:
                merged["canonical_url"] = clean.get("canonical_url") or clean.get("url") or row.get("url")
                merged["image_url"] = clean.get("image_url") or ""
                merged["ingredients"] = list(clean.get("ingredients") or [])
                merged["instructions"] = list(clean.get("instructions") or [])
                merged["has_instructions"] = bool(clean.get("instructions"))
                merged["instruction_count"] = len(clean.get("instructions") or [])
            rows.append(merged)
        return rows


def _read_summary(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _generated_at(summary: dict) -> str:
    value = summary.get("generated_at")
    return str(value) if value else now_iso()


def _authority(summary: dict, generated_at: str) -> dict:
    value = summary.get("authority")
    if (
        isinstance(value, dict)
        and value.get("authority_contract_version") == AUTHORITY_CONTRACT_VERSION
        and value.get("authoritative") is True
        and value.get("ranking_generated_at") == generated_at
    ):
        return dict(value)
    return {
        "authority_contract_version": AUTHORITY_CONTRACT_VERSION,
        "authoritative": False,
        "status": "refresh_required",
        "reason": "ranking_generation_requires_certification",
        "ranking_generated_at": generated_at,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Publish the complete mobile Recipe Intelligence corpus from existing local state without crawling the web."
    )
    parser.add_argument("--state", default="data/state.json")
    parser.add_argument("--leaderboard", default="output/leaderboard.csv")
    parser.add_argument("--summary", default="output/summary.json")
    parser.add_argument("--sources", default="config/sources.yaml")
    parser.add_argument("--docs", default="docs")
    parser.add_argument("--stale-days", type=int, default=14)
    parser.add_argument("--page-size", type=int, default=100)
    args = parser.parse_args()

    state_path = Path(args.state)
    state = json.loads(state_path.read_text(encoding="utf-8"))
    recipes_raw = state.get("recipes", {})
    if not isinstance(recipes_raw, dict):
        raise SystemExit("state.json does not contain a recipes mapping")
    recipes = {str(key): dict(value) for key, value in recipes_raw.items() if isinstance(value, dict)}
    ranked = _read_ranked(Path(args.leaderboard), recipes)
    sources = load_sources(args.sources)
    summary = _read_summary(Path(args.summary))
    generated_at = _generated_at(summary)
    authority = _authority(summary, generated_at)
    catalog = state.get("url_catalog", {})
    catalog_count = len(catalog) if isinstance(catalog, dict) else None

    manifest_path = write_app_feed(
        args.docs,
        generated_at,
        ranked,
        len(sources),
        corpus=list(recipes.values()),
        stale_days=args.stale_days,
        catalog_url_count=catalog_count,
        page_size=args.page_size,
    )
    manifest_target = Path(manifest_path)
    manifest = json.loads(manifest_target.read_text(encoding="utf-8"))
    manifest["authority"] = authority
    manifest["ranked_serving_available"] = authority.get("authoritative") is True
    manifest["ranked_serving_status"] = authority.get("status")
    manifest_target.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "manifest": manifest_path,
                "generated_at": generated_at,
                "ranked_recipe_count": manifest.get("ranked_recipe_count"),
                "corpus_recipe_count": manifest.get("corpus_recipe_count"),
                "corpus_status_counts": manifest.get("corpus_status_counts"),
                "catalog_url_count": manifest.get("catalog_url_count"),
                "authoritative": authority.get("authoritative"),
                "authority_status": authority.get("status"),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
