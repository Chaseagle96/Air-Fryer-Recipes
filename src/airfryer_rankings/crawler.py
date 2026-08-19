from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import fields, replace
from datetime import datetime, timezone
from typing import Any, Iterable

import requests

from .extract import extract_recipe_from_html
from .http import get, get_for_source, make_session, robots_and_sitemaps
from .models import UA, RecipeRow, SourceConfig, parse_dt


def _entry_age_hours(entry: dict, key: str, now: datetime) -> float:
    timestamp = parse_dt(entry.get(key))
    if not timestamp:
        return 1e9
    return max(0.0, (now - timestamp).total_seconds() / 3600)


def select_refresh_targets(
    state: dict,
    sources: Iterable[SourceConfig],
    mode: str,
    global_max_urls: int | None = None,
    hourly_limit: int = 100,
) -> list[dict]:
    source_map = {source.domain: source for source in sources}
    now = datetime.now(timezone.utc)
    catalog = [entry for entry in state.get("url_catalog", {}).values() if entry.get("source") in source_map]
    recipes = state.get("recipes", {})

    def score(entry: dict) -> tuple[float, float]:
        value = 0.0
        recipe = recipes.get(entry.get("recipe_id", ""), {})
        rank = int(recipe.get("last_rank") or 999999)
        if recipe.get("needs_evidence_backfill") or recipe.get("evidence_status") == "legacy_unverified":
            value += 100000
        if rank <= 100:
            value += 20000 - rank * 50
        if not entry.get("last_checked"):
            value += 15000
        if _entry_age_hours(entry, "first_discovered", now) <= 48:
            value += 8000
        if entry.get("priority") in {"modified", "changed", "legacy_evidence_backfill", "contract_changed"}:
            value += 7000
        if recipe.get("previous_rating_count") is not None:
            growth = int(recipe.get("rating_count", 0)) - int(recipe.get("previous_rating_count") or 0)
            if growth > 0:
                value += min(5000, growth * 10)
        age = _entry_age_hours(entry, "last_checked", now)
        value += min(4000, age * 10)
        return value, age

    if mode == "backfill":
        legacy = []
        for entry in catalog:
            recipe = recipes.get(entry.get("recipe_id", ""), {})
            if recipe.get("needs_evidence_backfill") or recipe.get("evidence_status") == "legacy_unverified":
                legacy.append(entry)
        return [dict(entry) for entry in sorted(legacy, key=score, reverse=True)]

    if mode == "hourly":
        ranked = sorted(catalog, key=score, reverse=True)
        return [dict(entry) for entry in ranked[:hourly_limit]]

    targets: list[dict] = []
    by_source: dict[str, list[dict]] = defaultdict(list)
    for entry in catalog:
        by_source[entry.get("source", "")].append(entry)
    for entries in by_source.values():
        cap = global_max_urls if global_max_urls is not None else len(entries)
        entries = sorted(entries, key=lambda entry: (_entry_age_hours(entry, "last_checked", now), score(entry)[0]), reverse=True)
        targets.extend(dict(entry) for entry in entries[:cap])
    return targets


def _row_from_existing(recipe: dict, retrieved_at: str, fetch_status: str = "not_modified") -> RecipeRow | None:
    if not recipe:
        return None
    names = {field.name for field in fields(RecipeRow)}
    payload = {key: value for key, value in recipe.items() if key in names}
    for key in ("ingredients", "instructions", "categories"):
        if key in payload and isinstance(payload[key], list):
            payload[key] = tuple(payload[key])
    try:
        row = RecipeRow(**payload)
        return replace(row, retrieved_at=retrieved_at, fetch_status=fetch_status)
    except Exception:
        return None


def _crawler_get(session, url: str, cfg: SourceConfig, timeout: int = 25, headers: dict | None = None):
    if cfg.origin == "discovered":
        return get_for_source(session, url, cfg, timeout, headers=headers)
    return get(session, url, timeout, headers=headers)


def crawl_targets(
    targets: Iterable[dict],
    sources: Iterable[SourceConfig],
    state: dict,
    run_at: str,
) -> tuple[list[RecipeRow], list[dict], list[dict]]:
    source_map = {source.domain: source for source in sources}
    grouped: dict[str, list[dict]] = defaultdict(list)
    for target in targets:
        grouped[target.get("source", "")].append(target)

    rows: list[RecipeRow] = []
    coverage: list[dict] = []
    events: list[dict] = []
    catalog = state.setdefault("url_catalog", {})
    recipes = state.setdefault("recipes", {})

    for domain, source_targets in grouped.items():
        cfg = source_map.get(domain)
        if not cfg:
            continue
        started = time.monotonic()
        session = make_session()
        parser, _, _, robots_status = robots_and_sitemaps(session, cfg)
        metrics: dict[str, Any] = {
            "source": domain,
            "targets": len(source_targets),
            "fetched": 0,
            "not_modified": 0,
            "verified_recipes": 0,
            "conflicts": 0,
            "missing": 0,
            "errors": 0,
            "http_403": 0,
            "http_429": 0,
            "dom_structure_changes": 0,
            "schema_structure_changes": 0,
            "legacy_backfill_targets": 0,
            "legacy_backfill_resolved": 0,
            "robots_status": robots_status,
            "status": "ok",
        }
        for target in source_targets:
            url = target["url"]
            entry = catalog.setdefault(url, dict(target))
            cached_recipe = recipes.get(entry.get("recipe_id", ""), {})
            force_evidence_refresh = bool(
                cached_recipe.get("needs_evidence_backfill") or cached_recipe.get("evidence_status") == "legacy_unverified"
            )
            if force_evidence_refresh:
                metrics["legacy_backfill_targets"] += 1
            try:
                if not parser.can_fetch(UA, url):
                    entry.update({"last_checked": run_at, "last_status": "robots_denied"})
                    events.append({"type": "robots_denied", "source": domain, "url": url, "timestamp": run_at})
                    continue
            except Exception:
                pass
            conditional = {}
            if not force_evidence_refresh:
                if entry.get("etag"):
                    conditional["If-None-Match"] = entry["etag"]
                if entry.get("last_modified"):
                    conditional["If-Modified-Since"] = entry["last_modified"]
            try:
                response = _crawler_get(session, url, cfg, 25, headers=conditional)
                if response.status_code == 304:
                    metrics["not_modified"] += 1
                    cached = recipes.get(entry.get("recipe_id", ""), {})
                    row = _row_from_existing(cached, run_at, "not_modified")
                    if row:
                        rows.append(row)
                        metrics["verified_recipes"] += 1
                    entry.update({"last_checked": run_at, "last_status": "not_modified", "priority": "stable"})
                    continue
                metrics["fetched"] += 1
                row, parse_meta = extract_recipe_from_html(response.text, url, domain, cfg, dict(response.headers))
                page_hash = parse_meta.get("page_hash", "")
                dom_fingerprint = parse_meta.get("dom_fingerprint", "")
                schema_signature = parse_meta.get("schema_signature", "")
                content_changed = bool(entry.get("page_hash") and page_hash and entry.get("page_hash") != page_hash)
                dom_changed = bool(
                    entry.get("dom_fingerprint")
                    and dom_fingerprint
                    and entry.get("dom_fingerprint") != dom_fingerprint
                )
                schema_changed = bool(
                    entry.get("schema_signature")
                    and schema_signature
                    and entry.get("schema_signature") != schema_signature
                )
                priority = "contract_changed" if dom_changed or schema_changed else "changed" if content_changed else "stable"
                entry.update(
                    {
                        "last_checked": run_at,
                        "last_status": "ok" if row else "no_verified_rating",
                        "etag": str(response.headers.get("ETag") or ""),
                        "last_modified": str(response.headers.get("Last-Modified") or ""),
                        "page_hash": page_hash,
                        "dom_fingerprint": dom_fingerprint,
                        "schema_signature": schema_signature,
                        "priority": priority,
                        "missing_count": 0,
                    }
                )
                if content_changed:
                    entry["last_changed"] = run_at
                if dom_changed:
                    metrics["dom_structure_changes"] += 1
                    events.append({"type": "dom_structure_changed", "source": domain, "url": url, "timestamp": run_at})
                if schema_changed:
                    metrics["schema_structure_changes"] += 1
                    events.append({"type": "schema_structure_changed", "source": domain, "url": url, "timestamp": run_at})
                for issue in parse_meta.get("issues", []):
                    events.append({"type": issue, "source": domain, "url": url, "timestamp": run_at})
                if row:
                    entry["recipe_id"] = row.recipe_id
                    rows.append(row)
                    metrics["verified_recipes"] += 1
                    if force_evidence_refresh and row.evidence_status != "legacy_unverified":
                        metrics["legacy_backfill_resolved"] += 1
                    if row.evidence_status == "conflict":
                        metrics["conflicts"] += 1
                else:
                    events.append({"type": "no_verified_rating", "source": domain, "url": url, "timestamp": run_at})
            except requests.HTTPError as exc:
                status = getattr(exc.response, "status_code", None)
                entry["last_checked"] = run_at
                entry["last_status"] = f"http_{status}" if status else "http_error"
                if status == 403:
                    metrics["http_403"] += 1
                if status == 429:
                    metrics["http_429"] += 1
                if status in (404, 410):
                    metrics["missing"] += 1
                    entry["missing_count"] = int(entry.get("missing_count", 0)) + 1
                    events.append({"type": "recipe_disappeared", "source": domain, "url": url, "status": status, "timestamp": run_at})
                else:
                    metrics["errors"] += 1
                    events.append({"type": "fetch_error", "source": domain, "url": url, "status": status, "timestamp": run_at})
            except Exception as exc:
                metrics["errors"] += 1
                entry.update({"last_checked": run_at, "last_status": f"error:{type(exc).__name__}"})
                events.append({"type": "fetch_error", "source": domain, "url": url, "error": type(exc).__name__, "timestamp": run_at})
            if cfg.delay > 0:
                time.sleep(cfg.delay)

        metrics["elapsed_seconds"] = round(time.monotonic() - started, 2)
        if metrics["errors"] and metrics["verified_recipes"] == 0:
            metrics["status"] = "degraded"
        coverage.append(metrics)
    return rows, coverage, events
