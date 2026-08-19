from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
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


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _valid_authority(value: object) -> dict | None:
    if (
        isinstance(value, dict)
        and isinstance(value.get("authoritative"), bool)
        and int(value.get("authority_contract_version") or 0) == AUTHORITY_CONTRACT_VERSION
    ):
        return dict(value)
    return None


def _authority(summary: dict, authority_path: Path | None = None) -> dict:
    embedded = _valid_authority(summary.get("authority"))
    if embedded is not None:
        return embedded
    if authority_path is not None:
        persisted = _valid_authority(_read_json(authority_path))
        if persisted is not None:
            return persisted
    return {
        "authority_contract_version": AUTHORITY_CONTRACT_VERSION,
        "authoritative": False,
        "status": "refresh_required",
        "reason": "missing_or_obsolete_authority_certificate",
    }


def _parse_dt(value: object) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _candidate_manifest_allowed(summary: dict, authority: dict) -> bool:
    """Allow an uncommitted candidate feed only for a genuinely newer ranking run.

    Production ranking workflows write a fresh summary, rebuild the mobile corpus,
    and then certify authority before any commit/deploy. A standalone corpus rebuild
    has no newer ranking generation, so it remains fail-closed after revocation.
    """

    if authority.get("authoritative") is True:
        return True
    generated_at = _parse_dt(summary.get("generated_at"))
    previous_ranking_at = _parse_dt(authority.get("last_ranking_generated_at"))
    return bool(generated_at and previous_ranking_at and generated_at > previous_ranking_at)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Publish the complete mobile Recipe Intelligence corpus from existing local state without crawling the web."
    )
    parser.add_argument("--state", default="data/state.json")
    parser.add_argument("--leaderboard", default="output/leaderboard.csv")
    parser.add_argument("--summary", default="output/summary.json")
    parser.add_argument("--authority", default="output/authority.json")
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
    summary = _read_json(Path(args.summary))
    generated_at = str(summary.get("generated_at") or now_iso())
    authority = _authority(summary, Path(args.authority))
    candidate_allowed = _candidate_manifest_allowed(summary, authority)
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
    serving_available = authority.get("authoritative") is True
    manifest["authority"] = authority
    manifest["ranked_serving_available"] = serving_available
    manifest["ranked_serving_status"] = authority.get("status")
    if not serving_available and not candidate_allowed:
        # Standalone corpus maintenance is never allowed to resurrect a revoked
        # ranking feed. Candidate pages exist only inside a newer ranking job and
        # cannot be committed because authority certification precedes publication.
        manifest["recipe_count"] = 0
        manifest["ranked_recipe_count"] = 0
        manifest["pages"] = []
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
                "ranked_serving_available": serving_available,
                "candidate_manifest": candidate_allowed and not serving_available,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
