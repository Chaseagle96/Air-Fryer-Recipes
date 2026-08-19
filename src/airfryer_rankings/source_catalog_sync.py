from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from .discovery import discover_source_urls
from .models import load_sources, now_iso
from .source_registry import effective_source_configs, load_source_registry
from .storage import load_state, save_state
from .url_normalization import normalize_url_catalog


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def _load_config(path: str | Path) -> dict[str, Any]:
    payload = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise ValueError("source discovery configuration must be a mapping")
    return payload


def _resolved_mode(config: dict[str, Any], requested: str) -> str:
    if requested in {"daily", "deep"}:
        return requested
    aggregate_path = Path(str(config.get("aggregate_output_path") or "output/source_expansion_all.json"))
    aggregate = _read_json(aggregate_path)
    mode = str(aggregate.get("mode") or "daily")
    return mode if mode in {"daily", "deep"} else "daily"


def _reconcile_activation_diagnostics(payload: dict[str, Any]) -> None:
    evaluations = payload.get("evaluations", []) or []
    if not isinstance(evaluations, list):
        return
    for row in evaluations:
        if isinstance(row, dict) and row.get("production_activation"):
            row["production_activation"] = (
                "effective allowlist immediately; persistent URL catalog synchronized after successful source expansion"
            )


def sync_promoted_source_catalogs(
    config_path: str | Path = "config/source_discovery.yaml",
    *,
    mode: str = "auto",
    dry_run: bool = False,
    run_at: str | None = None,
) -> dict[str, Any]:
    """Seed production-eligible discovered publishers into normalized URL catalogs.

    Source qualification owns trust decisions while this finalization step owns the
    narrow ranking-state mutation required by promotion: adding and canonicalizing
    URLs in ``url_catalog``. It never changes recipes, observations, priors, rankings,
    or historical evidence. Dynamic-source network requests continue through the
    SSRF-safe discovery path because their SourceConfig origin is ``discovered``.
    """

    config = _load_config(config_path)
    effective_mode = _resolved_mode(config, mode)
    timestamp = run_at or now_iso()
    budgets = config.get("budgets", {}) or {}
    mode_budget = budgets.get(effective_mode, {}) if isinstance(budgets, dict) else {}
    budget = mode_budget if isinstance(mode_budget, dict) else {}
    catalog_cap = int(budget.get("promotion_catalog_discovery_cap", 250))
    aggregate_path = Path(str(config.get("aggregate_output_path") or "output/source_expansion_all.json"))
    aggregate = _read_json(aggregate_path)
    aggregate_verticals = aggregate.setdefault("verticals", {})
    if not isinstance(aggregate_verticals, dict):
        aggregate_verticals = {}
        aggregate["verticals"] = aggregate_verticals

    summary: dict[str, Any] = {
        "generated_at": timestamp,
        "mode": effective_mode,
        "dry_run": dry_run,
        "verticals": {},
    }
    summary_verticals = summary["verticals"]
    assert isinstance(summary_verticals, dict)

    verticals = config.get("verticals", {}) or {}
    if not isinstance(verticals, dict):
        raise ValueError("source discovery verticals must be a mapping")

    for slug, raw_vertical in verticals.items():
        if not isinstance(raw_vertical, dict):
            continue
        vertical = dict(raw_vertical)
        sources_path = Path(str(vertical["base_sources_path"]))
        state_path = Path(str(vertical["state_path"]))
        registry_path = Path(str(vertical["registry_path"]))
        output_dir = Path(str(vertical["output_dir"]))

        base_sources = load_sources(sources_path, include_discovered=False)
        registry = load_source_registry(registry_path, str(slug))
        effective_sources = effective_source_configs(base_sources, registry)
        auto_sources = [source for source in effective_sources if source.origin == "discovered"]
        state = load_state(state_path)
        raw_before_count = len(state.get("url_catalog", {}) or {})
        normalization = normalize_url_catalog(state)
        normalized_before_count = len(state.get("url_catalog", {}) or {})
        results: list[dict[str, Any]] = []

        for source in auto_sources:
            result = discover_source_urls(
                source,
                state,
                effective_mode,
                timestamp,
                global_max_urls=catalog_cap,
            )
            results.append(result)

        after_normalization = normalize_url_catalog(state)
        after_count = len(state.get("url_catalog", {}) or {})
        added = max(0, after_count - normalized_before_count)
        coalesced = int(normalization["aliases_coalesced"]) + int(after_normalization["aliases_coalesced"])
        rewritten = int(normalization["urls_rewritten"]) + int(after_normalization["urls_rewritten"])
        changed = after_count != raw_before_count or rewritten > 0
        if not dry_run and changed:
            save_state(state_path, state)

        vertical_summary: dict[str, Any] = {
            "vertical": str(slug),
            "manual_source_count": len(base_sources),
            "auto_source_count": len(auto_sources),
            "effective_source_count": len(effective_sources),
            "catalog_url_count_before": raw_before_count,
            "catalog_url_count_after_normalization": normalized_before_count,
            "catalog_url_count_after": after_count,
            "catalog_urls_added": added,
            "catalog_urls_coalesced": coalesced,
            "catalog_urls_rewritten": rewritten,
            "catalog_net_change": after_count - raw_before_count,
            "sources": results,
        }
        summary_verticals[str(slug)] = vertical_summary

        metrics_path = output_dir / "source_expansion.json"
        metrics = _read_json(metrics_path)
        if metrics:
            _reconcile_activation_diagnostics(metrics)
            metrics["catalog_url_count"] = after_count
            metrics["catalog_urls_added_after_promotion"] = added
            metrics["catalog_urls_coalesced"] = coalesced
            metrics["catalog_urls_rewritten"] = rewritten
            metrics["catalog_net_change"] = after_count - raw_before_count
            metrics["catalog_sync_generated_at"] = timestamp
            metrics["catalog_sync"] = results
            if not dry_run:
                _write_json(metrics_path, metrics)

        aggregate_vertical = aggregate_verticals.get(str(slug))
        if isinstance(aggregate_vertical, dict):
            _reconcile_activation_diagnostics(aggregate_vertical)
            aggregate_vertical["catalog_url_count"] = after_count
            aggregate_vertical["catalog_urls_added_after_promotion"] = added
            aggregate_vertical["catalog_urls_coalesced"] = coalesced
            aggregate_vertical["catalog_urls_rewritten"] = rewritten
            aggregate_vertical["catalog_net_change"] = after_count - raw_before_count
            aggregate_vertical["catalog_sync_generated_at"] = timestamp
            aggregate_vertical["catalog_sync"] = results

    if not dry_run and aggregate:
        aggregate["catalog_sync_generated_at"] = timestamp
        _write_json(aggregate_path, aggregate)

    return summary
