from __future__ import annotations

import csv
import hashlib
import json
import re
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import SourceConfig, load_sources
from .source_registry import load_source_registry
from .storage import load_state

AUTHORITY_CONTRACT_VERSION = 1
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


def _catalog_fingerprint(state: dict[str, Any]) -> tuple[str, int]:
    catalog = state.get("url_catalog", {}) or {}
    rows: list[dict[str, str]] = []
    if isinstance(catalog, dict):
        for key, raw in sorted(catalog.items(), key=lambda item: str(item[0])):
            entry = raw if isinstance(raw, dict) else {}
            rows.append(
                {
                    "key": str(key),
                    "url": str(entry.get("url") or key),
                    "source": str(entry.get("source") or ""),
                }
            )
    return _canonical_hash(rows), len(rows)


def _effective_catalog_count(state: dict[str, Any], effective_sources: set[str]) -> int:
    catalog = state.get("url_catalog", {}) or {}
    if not isinstance(catalog, dict):
        return 0
    return sum(
        1
        for raw in catalog.values()
        if isinstance(raw, dict) and str(raw.get("source") or "").lower().strip() in effective_sources
    )


def _leaderboard_fingerprint(path: str | Path) -> str:
    target = Path(path)
    if not target.exists():
        raise AuthorityError(f"leaderboard missing: {target}")
    return hashlib.sha256(target.read_bytes()).hexdigest()


def _leaderboard_sources(path: str | Path, sources: list[SourceConfig]) -> set[str]:
    """Validate leaderboard source membership and any strict vertical semantics."""

    target = Path(path)
    if not target.exists():
        raise AuthorityError(f"leaderboard missing: {target}")
    source_map = {source.domain.lower().strip(): source for source in sources}
    leaderboard_sources: set[str] = set()
    vertical_mismatches: list[str] = []
    try:
        with target.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            if not reader.fieldnames or "source" not in reader.fieldnames:
                raise AuthorityError("leaderboard is missing required source column")
            for row in reader:
                source = str(row.get("source") or "").lower().strip()
                if not source:
                    continue
                leaderboard_sources.add(source)
                config = source_map.get(source)
                if config is None or config.allow_unmatched_discovery_links or not config.include_pattern:
                    continue
                haystack = f"{row.get('title', '')} {row.get('url', '')}"
                try:
                    matches_vertical = bool(re.search(config.include_pattern, haystack, re.I))
                except re.error as exc:
                    raise AuthorityError(f"invalid strict vertical include pattern for {source}: {exc}") from exc
                if not matches_vertical:
                    vertical_mismatches.append(f"{source}:{str(row.get('title') or row.get('url') or '')[:100]}")
    except UnicodeDecodeError as exc:
        raise AuthorityError(f"leaderboard is not valid UTF-8 CSV: {target}") from exc

    if vertical_mismatches:
        sample = ", ".join(vertical_mismatches[:10])
        raise AuthorityError("leaderboard contains recipes outside strict vertical policy: " + sample)
    return leaderboard_sources


def _update_manifest(path: str | Path | None, authority: dict[str, Any]) -> None:
    if not path:
        return
    target = Path(path)
    if not target.exists():
        return
    manifest = _read_json(target)
    if not manifest:
        return
    manifest["authority"] = authority
    _write_json(target, manifest)


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
    """Fail closed unless the serving leaderboard matches current production inputs.

    A changed source/catalog/model generation must first receive a genuinely complete
    known-catalog refresh. Once that baseline is certified, incremental runs may
    inherit authority while the exact input fingerprint remains unchanged.
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
    effective_source_set = {domain.lower().strip() for domain in source_domains}
    catalog_hash, catalog_count = _catalog_fingerprint(state)
    eligible_catalog_count = _effective_catalog_count(state, effective_source_set)

    summary_source_count = int(summary.get("configured_sources") or 0)
    summary_catalog_count = int(summary.get("catalog_urls") or 0)
    summary_eligible_catalog_count = int(summary.get("eligible_catalog_urls") or 0)
    if summary_source_count != len(sources):
        raise AuthorityError(f"source mismatch: summary={summary_source_count} current={len(sources)}")
    if summary_catalog_count != catalog_count:
        raise AuthorityError(f"catalog mismatch: summary={summary_catalog_count} current={catalog_count}")
    if summary_eligible_catalog_count != eligible_catalog_count:
        raise AuthorityError(
            "effective catalog mismatch: "
            f"summary={summary_eligible_catalog_count} current={eligible_catalog_count}"
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
    if catalog_count < metrics_catalog_count:
        raise AuthorityError(
            f"current catalog regressed below synchronized catalog: current={catalog_count} synced={metrics_catalog_count}"
        )

    leaderboard_sources = _leaderboard_sources(leaderboard_path, sources)
    unauthorized_sources = sorted(leaderboard_sources - effective_source_set)
    if unauthorized_sources:
        raise AuthorityError(
            "leaderboard contains non-effective sources: " + ", ".join(unauthorized_sources)
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
        and existing.get("input_fingerprint_sha256") == input_fingerprint
        and existing.get("catalog_sync_generated_at") == metrics.get("catalog_sync_generated_at")
    )
    run_mode = str(summary.get("mode") or "")
    if not inherited_input_authority:
        if run_mode not in FULL_REFRESH_MODES:
            raise AuthorityError(
                "new source/catalog/model generation requires a daily or deep refresh before certification"
            )
        if eligible_catalog_count <= 0:
            raise AuthorityError("cannot establish authority without an effective recipe catalog")
        targets_this_run = int(summary.get("targets_this_run") or 0)
        if targets_this_run != eligible_catalog_count:
            raise AuthorityError(
                "full authority baseline did not target the entire effective catalog: "
                f"targets={targets_this_run} effective_catalog={eligible_catalog_count}"
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
        "catalog_url_count": catalog_count,
        "eligible_catalog_url_count": eligible_catalog_count,
        "leaderboard_sources": sorted(leaderboard_sources),
        "source_fingerprint_sha256": source_hash,
        "catalog_fingerprint_sha256": catalog_hash,
        "input_fingerprint_sha256": input_fingerprint,
        "leaderboard_fingerprint_sha256": leaderboard_hash,
        "generation_fingerprint_sha256": generation_fingerprint,
        "source_expansion_generated_at": metrics.get("generated_at"),
        "catalog_sync_generated_at": metrics.get("catalog_sync_generated_at"),
        "ranking_generated_at": summary.get("generated_at"),
        "ranking_mode": run_mode,
        "ranked_recipe_count": int(summary.get("ranked_recipes") or 0),
        "model_version": summary.get("model_version"),
        "model_semver": summary.get("model_semver"),
    }

    summary["authority"] = authority
    _write_json(summary_path, summary)
    _write_json(authority_path, authority)
    if public_authority_path:
        _write_json(public_authority_path, authority)
    _update_manifest(manifest_path, authority)
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
    """Mark serving artifacts non-authoritative when upstream source state advances.

    A late invalidation is ignored when the current ranking is already newer than both
    the latest source-expansion and catalog-sync timestamps, preventing workflow races
    from incorrectly downgrading a freshly published generation.
    """

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
        if existing.get("authoritative") is True:
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
    _update_manifest(manifest_path, authority)
    return authority
