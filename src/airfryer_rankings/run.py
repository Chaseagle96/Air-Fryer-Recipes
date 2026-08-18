from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

from .core import (
    bayesian_rank,
    crawl_targets,
    detect_anomalies,
    discover_source_urls,
    load_sources,
    load_state,
    merge_observations,
    now_iso,
    read_recent_records,
    save_state,
    select_refresh_targets,
    source_reliability,
    write_run_records,
)
from .reporting import write_csv_outputs, write_dashboard, write_workbook


def _merge_coverage(sources, discovery: list[dict], crawl: list[dict]) -> list[dict]:
    d = {x.get("source"): x for x in discovery}
    c = {x.get("source"): x for x in crawl}
    output = []
    for cfg in sources:
        row = {"source": cfg.domain}
        row.update(d.get(cfg.domain, {}))
        crawl_row = c.get(cfg.domain, {})
        for key, value in crawl_row.items():
            if key in row and key not in {"source", "status"}:
                row[f"crawl_{key}"] = value
            else:
                row[key] = value
        if cfg.domain not in d and cfg.domain not in c:
            row["status"] = "not_checked_this_run"
        elif crawl_row.get("status") == "degraded":
            row["status"] = "degraded"
        else:
            row["status"] = row.get("status", "ok")
        output.append(row)
    return output


def main() -> None:
    ap = argparse.ArgumentParser(description="Incremental air-fryer recipe ranking pipeline")
    ap.add_argument("--sources", default="config/sources.yaml")
    ap.add_argument("--state", default="data/state.json")
    ap.add_argument("--mode", choices=("hourly", "daily", "deep", "smoke"), default="hourly")
    ap.add_argument("--max-urls", type=int, default=None, help="Per-source fetch cap override")
    ap.add_argument("--hourly-limit", type=int, default=100, help="Global hourly refresh target cap")
    ap.add_argument("--stale-days", type=int, default=14)
    args = ap.parse_args()

    Path("data/observations").mkdir(parents=True, exist_ok=True)
    Path("data/anomalies").mkdir(parents=True, exist_ok=True)
    Path("data/rankings").mkdir(parents=True, exist_ok=True)
    Path("data/coverage").mkdir(parents=True, exist_ok=True)
    Path("output").mkdir(exist_ok=True)
    Path("docs").mkdir(exist_ok=True)

    run_at = now_iso()
    state = load_state(args.state)
    sources = load_sources(args.sources)

    discovery_results: list[dict] = []
    should_discover = args.mode in {"daily", "deep", "smoke"} or not state.get("url_catalog")
    if should_discover:
        discovery_mode = "deep" if args.mode == "deep" else "daily"
        for cfg in sources:
            try:
                discovery_results.append(
                    discover_source_urls(cfg, state, discovery_mode, run_at, global_max_urls=args.max_urls)
                )
            except Exception as exc:
                discovery_results.append(
                    {
                        "source": cfg.domain,
                        "discovered_urls": 0,
                        "new_urls": 0,
                        "sitemap_docs": 0,
                        "elapsed_seconds": 0,
                        "status": f"discovery_error:{type(exc).__name__}",
                    }
                )

    target_mode = "daily" if args.mode == "smoke" else args.mode
    targets = select_refresh_targets(
        state,
        sources,
        target_mode,
        global_max_urls=args.max_urls,
        hourly_limit=args.hourly_limit,
    )
    rows, crawl_coverage, crawl_events = crawl_targets(targets, sources, state, run_at)
    observations = merge_observations(state, rows, run_at)
    coverage = _merge_coverage(sources, discovery_results, crawl_coverage)

    state.setdefault("source_history", []).append({"run_at": run_at, "mode": args.mode, "coverage": coverage})
    if len(state["source_history"]) > 720:
        del state["source_history"][:-720]

    anomalies = detect_anomalies(state, rows, coverage, crawl_events, run_at)
    ranked, method = bayesian_rank(state, stale_days=args.stale_days)
    reliability = source_reliability(state, coverage, method)

    observation_file = write_run_records("data/observations", observations, run_at)
    anomaly_file = write_run_records("data/anomalies", anomalies, run_at)
    coverage_file = write_run_records("data/coverage", coverage, run_at)
    ranking_snapshot = [
        {k: row.get(k) for k in ("rank", "recipe_id", "title", "source", "url", "rating", "rating_count", "hierarchical_score", "evidence_confidence", "duplicate_group_id")}
        for row in ranked[:200]
    ]
    ranking_file = write_run_records("data/rankings", ranking_snapshot, run_at)
    recent_observations = read_recent_records("data/observations", limit=5000)

    method_row = {
        "generated_at": run_at,
        "mode": args.mode,
        "observations_this_run": len(observations),
        "ranked_recipes": len(ranked),
        "configured_sources": len(sources),
        "catalog_urls": len(state.get("url_catalog", {})),
        "targets_this_run": len(targets),
        "global_prior": method.get("global_prior"),
        "volume_prior_m": method.get("volume_prior_m"),
        "candidate_count": method.get("candidate_count"),
        "deduplicated_count": method.get("deduplicated_count"),
        "stale_days": method.get("stale_days", args.stale_days),
        "history_snapshots": method.get("history_snapshots"),
        "formula": method.get("formula"),
        "prior_definition": "Global prior is sqrt(review-count)-weighted; publisher means are partially pooled toward the global prior before recipe-level Bayesian shrinkage.",
        "uncertainty_definition": "Conservative score subtracts a capped 95%-style maximum-variance uncertainty penalty from the posterior mean.",
        "evidence_definition": "Schema.org AggregateRating is cross-checked against visible/microdata evidence when available; conflicts are quarantined from ranking.",
        "dedupe_definition": "High-threshold fuzzy clustering uses title, normalized ingredients, instructions, author, canonical URL, and image-URL fingerprint. Cross-site review counts are NOT summed.",
        "history_definition": "Every successful rating observation is written as an immutable per-run NDJSON record under data/observations/.",
    }

    duplicate_groups = method.get("duplicate_groups", [])
    write_csv_outputs("output", ranked, coverage, reliability, anomalies)
    write_workbook(
        "output/air_fryer_rankings.xlsx",
        ranked,
        coverage,
        reliability,
        recent_observations,
        anomalies,
        duplicate_groups,
        method_row,
    )
    write_dashboard("docs", run_at, ranked, reliability, anomalies, method_row, len(sources))

    summary = {
        **method_row,
        "source_count": len(sources),
        "sources_ok": sum(1 for x in coverage if x.get("status") == "ok"),
        "observation_file": observation_file,
        "anomaly_file": anomaly_file,
        "coverage_file": coverage_file,
        "ranking_snapshot_file": ranking_file,
        "top10": ranked[:10],
        "coverage": coverage,
        "source_reliability": reliability,
        "anomalies": anomalies[:100],
        "source_adjustments": method.get("source_adjustments", {}),
    }
    Path("output/summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    save_state(args.state, state)


if __name__ == "__main__":
    main()
