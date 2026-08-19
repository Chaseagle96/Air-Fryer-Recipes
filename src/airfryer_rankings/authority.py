from __future__ import annotations

import hashlib
import html
import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import SourceConfig, load_sources
from .source_registry import load_source_registry
from .storage import load_state

AUTHORITY_CONTRACT_VERSION = 2
FULL_REFRESH_MODES = {"daily", "deep"}


class AuthorityError(RuntimeError):
    """Raised when a serving artifact does not match current production inputs."""


def _read_json(path: str | Path) -> dict[str, Any]:
    target = Path(path)
    if not target.exists():
        return {}
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_json(path: str | Path, payload: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _canonical_hash(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _source_fingerprint(sources: list[SourceConfig]) -> tuple[str, list[str]]:
    rows = []
    for source in sorted(sources, key=lambda item: item.domain):
        payload = asdict(source)
        payload["sitemap_urls"] = list(source.sitemap_urls)
        payload["discovery_urls"] = list(source.discovery_urls)
        rows.append(payload)
    return _canonical_hash(rows), [source.domain for source in sorted(sources, key=lambda item: item.domain)]


def _catalog_fingerprint(
    state: dict[str, Any],
    allowed_sources: set[str],
) -> tuple[str, int]:
    catalog = state.get("url_catalog", {}) or {}
    rows: list[dict[str, str]] = []
    if isinstance(catalog, dict):
        for key, raw in sorted(catalog.items(), key=lambda item: str(item[0])):
            entry = raw if isinstance(raw, dict) else {}
            source = str(entry.get("source") or "")
            if source not in allowed_sources:
                continue
            rows.append(
                {
                    "key": str(key),
                    "url": str(entry.get("url") or key),
                    "source": source,
                }
            )
    return _canonical_hash(rows), len(rows)


def _leaderboard_fingerprint(path: str | Path) -> str:
    target = Path(path)
    if not target.exists():
        raise AuthorityError(f"leaderboard missing: {target}")
    return hashlib.sha256(target.read_bytes()).hexdigest()


def _update_manifest(
    path: str | Path | None,
    authority: dict[str, Any],
    *,
    serving_available: bool,
) -> None:
    if not path:
        return
    target = Path(path)
    if not target.exists():
        return
    manifest = _read_json(target)
    if not manifest:
        return
    manifest["authority"] = authority
    manifest["ranked_serving_available"] = serving_available
    manifest["ranked_serving_status"] = authority.get("status")
    if not serving_available:
        # Keep the broader corpus metadata for research/exploration, but remove every
        # standard Discover pointer so clients cannot accidentally serve stale ranks.
        manifest["recipe_count"] = 0
        manifest["ranked_recipe_count"] = 0
        manifest["pages"] = []
    _write_json(target, manifest)


def _write_unavailable_dashboard(
    manifest_path: str | Path | None,
    authority: dict[str, Any],
) -> None:
    if not manifest_path:
        return
    manifest = Path(manifest_path)
    docs_root = manifest.parent.parent
    if not docs_root.exists():
        return
    dashboard = docs_root / "index.html"
    vertical = html.escape(str(authority.get("vertical") or "Recipe Intelligence"))
    invalidated_at = html.escape(str(authority.get("invalidated_at") or "unknown"))
    reason = html.escape(str(authority.get("reason") or "ranking authority invalidated"))
    dashboard.write_text(
        "<!doctype html>\n"
        '<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        "<title>Recipe Intelligence - Rankings Refreshing</title></head>\n"
        "<body><main>"
        "<h1>Rankings temporarily unavailable</h1>"
        "<p>The previous ranked generation is not authoritative. Recipe Intelligence "
        "will publish rankings again only after a complete current-corpus refresh passes "
        "the authority contract.</p>"
        f"<p><strong>Vertical:</strong> {vertical}</p>"
        f"<p><strong>Status:</strong> refresh_required</p>"
        f"<p><strong>Reason:</strong> {reason}</p>"
        f"<p><strong>Invalidated at:</strong> {invalidated_at}</p>"
        "</main></body></html>\n",
        encoding="utf-8",
    )


def publish_authority(
    *,
    vertical: str,
    sources_path: str | Path,
    state_path: str | Path,
    registry_path: str | Path,
    metrics_path: str | Path,
    summary_path: str | Path,
    leaderboard_path: str | Path,
    authority_path: str | Path,
    public_authority_path: str | Path | None = None,
    manifest_path: str | Path | None = None,
) -> dict[str, Any]:
    """Certify only a ranking built from the current effective production universe.

    New source/catalog/model generations require a measured full-catalog daily or deep
    refresh. Hourly runs may inherit authority only when that exact input fingerprint
    is unchanged from an already certified baseline.
    """

    summary = _read_json(summary_path)
    metrics = _read_json(metrics_path)
    if not summary:
        raise AuthorityError(f"summary missing or invalid: {summary_path}")
    if not metrics:
        raise AuthorityError(f"source-expansion metrics missing or invalid: {metrics_path}")

    sources = load_sources(sources_path)
    state = load_state(state_path)
    registry = load_source_registry(registry_path, vertical)
    source_hash, source_domains = _source_fingerprint(sources)
    allowed_sources = set(source_domains)
    catalog_hash, effective_catalog_count = _catalog_fingerprint(state, allowed_sources)
    raw_catalog_count = len(state.get("url_catalog", {}) or {})

    summary_source_count = int(summary.get("configured_sources") or 0)
    summary_catalog_count = int(summary.get("catalog_urls") or 0)
    if summary_source_count != len(sources):
        raise AuthorityError(f"source mismatch: summary={summary_source_count} current={len(sources)}")
    if summary_catalog_count != raw_catalog_count:
        raise AuthorityError(f"catalog mismatch: summary={summary_catalog_count} current={raw_catalog_count}")

    ranking_scope = state.get("effective_source_domains")
    persisted_source_domains = sorted(
        {str(domain) for domain in ranking_scope if str(domain)}
    ) if isinstance(ranking_scope, list) else []
    if persisted_source_domains != source_domains:
        raise AuthorityError(
            "ranking source scope does not match current effective allowlist: "
            f"ranking={persisted_source_domains} current={source_domains}"
        )

    source_gate_version = int(registry.get("source_gate_version") or 0)
    metrics_gate_version = int(metrics.get("source_gate_version") or 0)
    if source_gate_version <= 0 or metrics_gate_version != source_gate_version:
        raise AuthorityError(
            f"source gate mismatch: registry={source_gate_version} metrics={metrics_gate_version}"
        )

    expansion_at = _parse_dt(metrics.get("generated_at"))
    catalog_sync_at = _parse_dt(metrics.get("catalog_sync_generated_at"))
    ranking_at = _parse_dt(summary.get("generated_at"))
    if expansion_at is None:
        raise AuthorityError("source-expansion generated_at is missing")
    if catalog_sync_at is None or catalog_sync_at < expansion_at:
        raise AuthorityError(
            "catalog synchronization does not postdate the latest source-expansion generation"
        )
    if ranking_at is None or ranking_at < catalog_sync_at:
        raise AuthorityError("ranking generation predates the latest catalog synchronization")

    metrics_catalog_count = int(metrics.get("catalog_url_count") or 0)
    if raw_catalog_count < metrics_catalog_count:
        raise AuthorityError(
            f"current catalog regressed below synchronized catalog: current={raw_catalog_count} synced={metrics_catalog_count}"
        )

    input_fingerprint = _canonical_hash(
        {
            "authority_contract_version": AUTHORITY_CONTRACT_VERSION,
            "vertical": vertical,
            "source_gate_version": source_gate_version,
            "source_fingerprint": source_hash,
            "catalog_fingerprint": catalog_hash,
            "model_semver": str(summary.get("model_semver") or ""),
        }
    )
    existing = _read_json(authority_path)
    inherited_input_authority = (
        existing.get("authoritative") is True
        and existing.get("authority_contract_version") == AUTHORITY_CONTRACT_VERSION
        and existing.get("input_fingerprint_sha256") == input_fingerprint
        and existing.get("catalog_sync_generated_at") == metrics.get("catalog_sync_generated_at")
    )
    run_mode = str(summary.get("mode") or "")
    targets_this_run = int(summary.get("targets_this_run") or 0)
    if not inherited_input_authority:
        if run_mode not in FULL_REFRESH_MODES:
            raise AuthorityError(
                "new source/catalog/model generation requires a daily or deep refresh before certification"
            )
        if targets_this_run < effective_catalog_count:
            raise AuthorityError(
                "new generation did not attempt the complete effective catalog: "
                f"targets={targets_this_run} effective_catalog={effective_catalog_count}"
            )

    leaderboard_hash = _leaderboard_fingerprint(leaderboard_path)
    generation_fingerprint = _canonical_hash(
        {
            "input_fingerprint": input_fingerprint,
            "leaderboard_fingerprint": leaderboard_hash,
            "ranking_generated_at": summary.get("generated_at"),
        }
    )

    authority: dict[str, Any] = {
        "authority_contract_version": AUTHORITY_CONTRACT_VERSION,
        "authoritative": True,
        "status": "authoritative",
        "vertical": vertical,
        "source_gate_version": source_gate_version,
        "effective_source_count": len(sources),
        "effective_sources": source_domains,
        "effective_catalog_url_count": effective_catalog_count,
        "raw_catalog_url_count": raw_catalog_count,
        "source_fingerprint_sha256": source_hash,
        "catalog_fingerprint_sha256": catalog_hash,
        "input_fingerprint_sha256": input_fingerprint,
        "leaderboard_fingerprint_sha256": leaderboard_hash,
        "generation_fingerprint_sha256": generation_fingerprint,
        "source_expansion_generated_at": metrics.get("generated_at"),
        "catalog_sync_generated_at": metrics.get("catalog_sync_generated_at"),
        "ranking_generated_at": summary.get("generated_at"),
        "ranking_mode": run_mode,
        "targets_this_run": targets_this_run,
        "full_catalog_baseline": not inherited_input_authority,
        "ranked_recipe_count": int(summary.get("ranked_recipes") or 0),
        "model_version": summary.get("model_version"),
        "model_semver": summary.get("model_semver"),
    }

    summary["authority"] = authority
    _write_json(summary_path, summary)
    _write_json(authority_path, authority)
    if public_authority_path:
        _write_json(public_authority_path, authority)
    _update_manifest(manifest_path, authority, serving_available=True)
    return authority


def invalidate_authority(
    *,
    vertical: str,
    metrics_path: str | Path,
    summary_path: str | Path,
    authority_path: str | Path,
    public_authority_path: str | Path | None = None,
    manifest_path: str | Path | None = None,
    reason: str = "source_or_catalog_generation_advanced",
    invalidated_at: str | None = None,
) -> dict[str, Any]:
    summary = _read_json(summary_path)
    metrics = _read_json(metrics_path)
    ranking_at = _parse_dt(summary.get("generated_at"))
    expansion_at = _parse_dt(metrics.get("generated_at"))
    catalog_sync_at = _parse_dt(metrics.get("catalog_sync_generated_at"))
    newest_input_at = max(
        (value for value in (expansion_at, catalog_sync_at) if value is not None),
        default=None,
    )

    existing = _read_json(authority_path)
    if ranking_at is not None and newest_input_at is not None and ranking_at >= newest_input_at:
        if (
            existing.get("authoritative") is True
            and existing.get("authority_contract_version") == AUTHORITY_CONTRACT_VERSION
        ):
            return existing

    timestamp = invalidated_at or datetime.now(timezone.utc).isoformat()
    authority: dict[str, Any] = {
        "authority_contract_version": AUTHORITY_CONTRACT_VERSION,
        "authoritative": False,
        "status": "refresh_required",
        "vertical": vertical,
        "reason": reason,
        "invalidated_at": timestamp,
        "source_expansion_generated_at": metrics.get("generated_at"),
        "catalog_sync_generated_at": metrics.get("catalog_sync_generated_at"),
        "last_ranking_generated_at": summary.get("generated_at"),
    }
    if summary:
        summary["authority"] = authority
        _write_json(summary_path, summary)
    _write_json(authority_path, authority)
    if public_authority_path:
        _write_json(public_authority_path, authority)
    _update_manifest(manifest_path, authority, serving_available=False)
    _write_unavailable_dashboard(manifest_path, authority)
    return authority
