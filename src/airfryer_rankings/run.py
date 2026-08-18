from __future__ import annotations

import argparse
import json
from pathlib import Path

from .analytics import write_duckdb_cache
from .benchmarks import evaluate_dedupe_benchmark
from .calibration import build_empirical_uncertainty, build_historical_metrics
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
    source_health_summary,
    source_reliability,
    write_run_records,
)
from .media import enrich_ambiguous_perceptual_hashes
from .reporting import write_csv_outputs, write_dashboard, write_workbook

MAX_ANALYTICAL_RECORDS = 250000
MAX_EXCEL_OBSERVATIONS = 10000


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
    ap.add_argument("--mode", choices=("hourly", "daily", "deep", "smoke", "backfill"), default="hourly")
    ap.add_argument("--max-urls", type=int, default=None, help="Per-source fetch cap override")
    ap.add_argument("--hourly-limit", type=int, default=100, help="Global hourly refresh target cap")
    ap.add_argument("--stale-days", type=int, default=14)
    args = ap.parse_args()

    for folder in ("data/observations", "data/anomalies", "data/rankings", "data/coverage", "output", "docs"):
        Path(folder).mkdir(parents=True, exist_ok=True)

    run_at = now_iso()
    state = load_state(args.state)
    sources = load_sources(args.sources)
    migration = state.get("migration", {})
    requested_mode = args.mode
    effective_mode = args.mode
    if requested_mode == "hourly" and int(migration.get("legacy_evidence_pending") or 0) > 0:
        effective_mode = "backfill"

    discovery_results: list[dict] = []
    should_discover = effective_mode in {"daily", "deep", "smoke"} or not state.get("url_catalog")
    if should_discover:
        discovery_mode = "deep" if effective_mode == "deep" else "daily"
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

    target_mode = "daily" if effective_mode == "smoke" else effective_mode
    targets = select_refresh_targets(
        state,
        sources,
        target_mode,
        global_max_urls=args.max_urls,
        hourly_limit=args.hourly_limit,
    )
    rows, crawl_coverage, crawl_events = crawl_targets(targets, sources, state, run_at)
    media_stats = enrich_ambiguous_perceptual_hashes(rows, state, max_fetches=20)
    observations = merge_observations(state, rows, run_at)
    coverage = _merge_coverage(sources, discovery_results, crawl_coverage)

    state.setdefault("source_history", []).append({"run_at": run_at, "mode": effective_mode, "coverage": coverage})
    if len(state["source_history"]) > 720:
        del state["source_history"][:-720]

    anomalies = detect_anomalies(state, rows, coverage, crawl_events, run_at)
    prior_observations = read_recent_records("data/observations", limit=MAX_ANALYTICAL_RECORDS)
    prior_rankings = read_recent_records("data/rankings", limit=MAX_ANALYTICAL_RECORDS)
    all_observations = (prior_observations + observations)[-MAX_ANALYTICAL_RECORDS:]
    uncertainty_calibration = build_empirical_uncertainty(all_observations)
    historical_metrics = build_historical_metrics(all_observations, prior_rankings)
    ranked, method = bayesian_rank(
        state,
        stale_days=args.stale_days,
        empirical_calibration=uncertainty_calibration,
        historical_metrics=historical_metrics,
    )
    reliability = source_reliability(state, coverage, method)
    source_health, health_summary = source_health_summary(state, coverage, sources, run_at)
    dedupe_benchmark, dedupe_benchmark_rows = evaluate_dedupe_benchmark("data/benchmarks/dedupe_pairs.json")

    observation_file = write_run_records("data/observations", observations, run_at)
    anomaly_file = write_run_records("data/anomalies", anomalies, run_at)
    coverage_file = write_run_records("data/coverage", coverage, run_at)
    ranking_snapshot = [
        {
            "timestamp": run_at,
            **{k: row.get(k) for k in (
                "rank", "recipe_id", "title", "source", "url", "rating", "rating_count",
                "hierarchical_score", "evidence_confidence", "evidence_grade", "rank_confidence",
                "rank_range_low", "rank_range_high", "duplicate_group_id",
            )},
        }
        for row in ranked[:200]
    ]
    ranking_file = write_run_records("data/rankings", ranking_snapshot, run_at)
    recent_rankings = (prior_rankings + ranking_snapshot)[-MAX_ANALYTICAL_RECORDS:]

    calibration_ready = sum(1 for x in uncertainty_calibration.values() if x.get("ready"))
    migration_after = state.get("migration", {})
    method_row = {
        "generated_at": run_at,
        "requested_mode": requested_mode,
        "mode": effective_mode,
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
        "robustness_simulations": method.get("robustness", {}).get("simulation_count"),
        "mean_spearman_top200": method.get("robustness", {}).get("mean_spearman_top200"),
        "mean_kendall_top100": method.get("robustness", {}).get("mean_kendall_top100"),
        "uncertainty_buckets_empirically_ready": calibration_ready,
        "legacy_evidence_pending": migration_after.get("legacy_evidence_pending"),
        "dedupe_benchmark_precision": dedupe_benchmark.get("precision"),
        "dedupe_benchmark_recall": dedupe_benchmark.get("recall"),
        "dedupe_benchmark_f1": dedupe_benchmark.get("f1"),
        "formula": method.get("formula"),
        "prior_definition": "Global prior is sqrt(review-count)-weighted. Publisher leniency is estimated from residuals after category baselines, then partially pooled and capped before recipe-level Bayesian shrinkage.",
        "uncertainty_definition": "Uses rating histograms when available, empirical historical rating volatility once a volume bucket has at least 30 observation pairs, otherwise a conservative theoretical fallback.",
        "evidence_definition": "Schema.org AggregateRating is cross-checked against visible/microdata evidence when available. Legacy rows are explicitly tagged and forced through backfill instead of inheriting the former 0.85 default.",
        "dedupe_definition": "High-threshold fuzzy clustering uses titles, normalized ingredients, instruction Jaccard + SimHash, author, canonical URL, and bounded perceptual image hashing. Cross-site review counts are not summed.",
        "robustness_definition": "Each production leaderboard is stress-tested across 36 plausible combinations of source-bias cap, evidence penalty, Bayesian prior strength, and uncertainty cap; rank ranges and confidence are reported per recipe.",
        "history_definition": "Immutable NDJSON remains the audit source of truth; DuckDB is rebuilt as a derived analytical cache. Excel exposes only the most recent 10,000 raw observations for usability.",
    }

    duplicate_groups = method.get("duplicate_groups", [])
    robustness = method.get("robustness", {})
    write_csv_outputs(
        "output",
        ranked,
        coverage,
        reliability,
        anomalies,
        source_health=source_health,
        robustness=robustness.get("simulations", []),
        dedupe_benchmark=dedupe_benchmark_rows,
    )
    write_workbook(
        "output/air_fryer_rankings.xlsx",
        ranked,
        coverage,
        reliability,
        all_observations[-MAX_EXCEL_OBSERVATIONS:],
        anomalies,
        duplicate_groups,
        method_row,
        source_health=source_health,
        uncertainty_calibration=list(uncertainty_calibration.values()),
        robustness=robustness.get("simulations", []),
        dedupe_benchmark=dedupe_benchmark_rows,
    )
    write_dashboard("docs", run_at, ranked, reliability, anomalies, method_row, len(sources))
    analytics_file = write_duckdb_cache(
        "output/air_fryer_analytics.duckdb",
        ranked=ranked,
        observations=all_observations,
        ranking_records=recent_rankings,
        source_health=source_health,
        source_reliability=reliability,
        anomalies=anomalies,
        calibration=uncertainty_calibration,
        robustness=robustness,
        dedupe_summary=dedupe_benchmark,
        dedupe_results=dedupe_benchmark_rows,
    )

    summary = {
        **method_row,
        **health_summary,
        "migration": migration_after,
        "media_enrichment": media_stats,
        "dedupe_benchmark": dedupe_benchmark,
        "uncertainty_calibration": uncertainty_calibration,
        "robustness": {k: v for k, v in robustness.items() if k != "simulations"},
        "observation_file": observation_file,
        "anomaly_file": anomaly_file,
        "coverage_file": coverage_file,
        "ranking_snapshot_file": ranking_file,
        "analytics_cache_file": analytics_file,
        "top10": ranked[:10],
        "coverage": coverage,
        "source_health": source_health,
        "source_reliability": reliability,
        "anomalies": anomalies[:100],
        "source_adjustments": method.get("source_adjustments", {}),
        "category_baselines": method.get("category_baselines", {}),
    }
    Path("output/summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    save_state(args.state, state)


if __name__ == "__main__":
    main()
