# Recipe Intelligence

[![Recipe Intelligence](https://github.com/Chaseagle96/Recipe-Intelligence/actions/workflows/hourly.yml/badge.svg)](https://github.com/Chaseagle96/Recipe-Intelligence/actions/workflows/hourly.yml)
[![CodeQL](https://github.com/Chaseagle96/Recipe-Intelligence/actions/workflows/codeql.yml/badge.svg)](https://github.com/Chaseagle96/Recipe-Intelligence/actions/workflows/codeql.yml)
[![Release](https://img.shields.io/github/v/release/Chaseagle96/Recipe-Intelligence)](https://github.com/Chaseagle96/Recipe-Intelligence/releases/latest)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**Current release: 5.2.0**  
**Current production vertical: Air Fryer**

Recipe Intelligence is an auditable, evidence-driven recipe research and ranking platform. It verifies public recipe-rating evidence, normalizes publisher behavior, applies Bayesian ranking with explicit uncertainty, detects duplicate/syndicated recipes, tracks longitudinal changes, and publishes reproducible ranking artifacts.

Air Fryer is the first production vertical. The repository identity is intentionally broader so additional cooking-method verticals such as Slow Cooker can reuse the same research, evidence, QA, storage, and ranking infrastructure while retaining vertical-specific discovery, calibration, and outputs.

## Platform architecture

Recipe Intelligence treats recipe ranking as a research and production data pipeline with four explicit contracts:

1. **Raw evidence**: immutable observations under `data/observations/`. This is the longitudinal source of truth.
2. **Clean state**: validated current recipe evidence in `data/state.json`. Individual clean recipe records are schema-versioned independently from the state envelope.
3. **Model outputs**: immutable ranking snapshots under `data/rankings/`, generated from a frozen versioned model configuration.
4. **Serving outputs**: CSV, Excel, DuckDB, JSON, and dashboard artifacts under `output/` and `docs/`.

Derived layers can be regenerated. Raw observation history is never rewritten to make it agree with a later model.

### Vertical model

The platform identity is broader than the current corpus. In release 5.2.0, **Air Fryer is the only production ranking vertical**.

Future verticals should share platform infrastructure while preserving their own:

- discovery/source configuration;
- recipe eligibility rules;
- calibration and category baselines where needed;
- historical validation context;
- serving/output namespace.

This prevents a Slow Cooker population, for example, from being naively mixed into Air Fryer priors or publisher/category expectations while still avoiding duplicated infrastructure.

### Ranking model

The active model is versioned in `config/model.yaml`. Production parameters never self-modify.

For each eligible recipe, the current model:

1. normalizes the publisher rating to a five-star scale;
2. estimates a square-root-volume-weighted global prior;
3. estimates partially pooled category baselines;
4. estimates publisher rating-system residuals after category expectations;
5. partially pools and caps publisher adjustment;
6. computes a Bayesian posterior using rating volume;
7. subtracts histogram, empirical-history, or conservative theoretical uncertainty;
8. subtracts an evidence-quality penalty when evidence is below the preferred tier;
9. calculates rank provenance and robustness diagnostics.

Conceptually:

`hierarchical_score = BayesianPosterior(category-aware source-adjusted rating) - uncertainty - evidence penalty`

Popularity growth is descriptive and does not directly boost the primary quality score.

### Ranking robustness

Every leaderboard is stress-tested across 36 nearby parameter configurations. The system reports:

- Top-200 Spearman correlation;
- Top-100 Kendall correlation;
- Top-10 and Top-50 overlap;
- per-recipe rank standard deviation;
- likely rank range;
- Top-10 and Top-50 frequency;
- `rank_confidence` from 0 to 1.

A deterministic golden-ranking fixture ensures scoring changes create a reviewable CI diff rather than silent rank drift.

### Historical predictive backtesting

Daily/deep runs can evaluate frozen candidate configurations over 30-, 60-, and 90-day horizons against later high-volume evidence and report future-quality rank correlation, posterior/final-score error, and future Top-10 overlap.

Backtesting remains disabled until enough longitudinal history exists. `config/model.yaml` defines minimum history/windows/recipe coverage, and `automatic_parameter_promotion` is explicitly false. Recommendations remain advisory until changed through a reviewed model-version update.

### Time-aware diagnostics

Observation history supports review growth, rating/review slopes, velocity, acceleration, material page changes, change-point detection, peak rank, time in Top 10/Top 50, and rank volatility. These signals aid interpretation and anomaly detection without turning virality into quality.

## Evidence integrity

Primary extraction uses Schema.org `Recipe` / `AggregateRating` JSON-LD and independently visible/microdata evidence when available.

Evidence states include:

- `verified`
- `schema_only`
- `visible_only`
- `conflict`
- `legacy_unverified`

Conflicted/sub-threshold evidence is quarantined. Legacy evidence is explicitly downgraded and force-refetched instead of inheriting an obsolete favorable default.

### Structural publisher contracts

Every fetched page records its page content hash, structural DOM fingerprint, JSON-LD schema signature, and visible rating-evidence shape. Publisher markup changes therefore generate QA/observability events even when the HTTP request itself succeeds.

### Reviewed real-page fixtures

`tests/fixtures/real_pages/` contains sanitized structural snapshots tied to real publisher pages. Weekly deep runs can capture candidate fixtures from configured publishers into an Actions artifact, but candidates never overwrite checked-in fixtures automatically.

### Evidence-confidence calibration

`data/benchmarks/evidence_labels.json` contains reviewed fixture expectations. Empirical evidence confidence activates only after the configured minimum reviewed sample size is reached, so small seed samples cannot masquerade as calibrated probabilities.

## Duplicate detection

Cross-site dedupe is deliberately precision-oriented. Signals include canonical URL, normalized title, ingredient overlap, instruction similarity/SimHash, author agreement, image URL fingerprint, and bounded perceptual image hashing for ambiguous candidates.

Cross-site review counts are **never summed** because syndicated pages may share a review population.

`data/benchmarks/dedupe_pairs.json` is the versioned adjudicated validation set. CI enforces benchmark quality floors, while `output/dedupe_label_queue.csv` surfaces ambiguous real-corpus candidates nearest the production threshold for human review.

## Observability and fail-closed publishing

Pipeline metrics include crawl/extraction success, ranking eligibility, evidence-conflict rate, robots denials, HTTP 403/429 counts, fetch latency, source freshness, structural publisher changes, legacy-evidence backlog, and anomaly volume.

Before a production result is committed, a versioned publication gate checks for catastrophic regressions such as an empty leaderboard, major corpus collapse, inability to produce a Top 50, severe evidence conflicts, unexplained rank collapse, or implausible dedupe expansion.

Warnings expose degraded-but-publishable runs. Failures stop production publication and preserve the prior serving state while diagnostic artifacts remain available.

## Historical storage

`config/storage.yaml` defines the storage contract.

- Git-backed NDJSON remains authoritative today.
- `output/air_fryer_analytics.duckdb` is the current Air Fryer vertical's regenerable analytical cache.
- Weekly deep runs can generate a compressed Parquet history archive artifact.
- Storage health reports NDJSON records/bytes and recommends archival migration once configured thresholds are crossed.
- External object-storage upload remains disabled unless explicitly configured.

The platform therefore has a path away from unbounded Git history without prematurely introducing external infrastructure.

## Current Air Fryer outputs

The existing output namespace remains Air Fryer-specific until a second production vertical is introduced. This is intentional migration safety, not repository branding.

### Repository/current data

- `output/top50.csv`
- `output/leaderboard.csv`
- `output/source_coverage.csv`
- `output/source_health.csv`
- `output/source_reliability.csv`
- `output/ranking_robustness.csv`
- `output/dedupe_benchmark.csv`
- `output/dedupe_label_queue.csv`
- `output/pipeline_metrics.csv`
- `output/historical_backtest.csv`
- `output/hyperparameter_evaluation.csv`
- `output/evidence_calibration.csv`
- `output/evidence_label_results.csv`
- `output/publication_quality_gate.csv`
- `output/quality_gate.json`
- `output/pipeline_metrics.json`
- `output/storage_health.json`
- `output/anomalies.csv`
- `output/summary.json`
- `data/contracts.json`
- `data/state.json`
- immutable `data/observations/`, `data/rankings/`, `data/coverage/`, and `data/anomalies/`

### Excel artifact

The workbook includes Top 50, all rankings, rank explainability, source coverage/health/reliability, rating history/trends, time signals, uncertainty/evidence calibration, robustness simulations, historical backtests, hyperparameter evaluation, pipeline metrics, publication gate, storage health, data contracts, movers, entrants, QA anomalies, duplicate groups, dedupe benchmark/label queue, methodology, and category leaderboards.

### Analytical artifacts

- `air_fryer_analytics.duckdb`: current Air Fryer vertical analytical database
- `history_archive.parquet`: compressed deep-run historical archive when generated
- `sbom.json`: CycloneDX software bill of materials
- `fixture-candidates`: sanitized publisher regression-fixture candidates from deep runs

## Continuous integration and supply-chain controls

The primary Recipe Intelligence workflow runs:

1. pinned dependency installation;
2. vulnerability audit and CycloneDX SBOM generation;
3. Ruff linting;
4. mypy static analysis;
5. pytest with branch coverage gate;
6. bounded live publisher smoke crawl;
7. Excel/DuckDB generation;
8. publication-gate evaluation.

GitHub Actions are pinned to exact commit SHAs. CodeQL runs independently. Dependabot monitors Python dependencies and Actions references.

The test suite combines deterministic unit/regression tests, reviewed real-page fixture tests, Hypothesis property tests, benchmark quality floors, and golden model-output tests.

## Refresh cadence

For the current Air Fryer vertical:

- `17 * * * *`: hourly incremental refresh
- `43 8 * * *`: daily discovery/full-known-catalog refresh plus backtest evaluation
- `13 9 * * 0`: weekly deep discovery/refresh, storage archive, and candidate fixture capture
- manual: `hourly`, `daily`, `deep`, or `backfill`
- pull requests: static/security/test gates plus bounded live smoke crawl without production writes

## Running locally

The distribution is now branded **Recipe Intelligence**. The internal `airfryer_rankings` Python namespace remains in release 5.2.x because it represents the existing Air Fryer implementation and avoids a high-risk import migration solely for branding.

```bash
python -m pip install -r requirements-dev.txt
ruff check src tests
mypy src/airfryer_rankings
PYTHONPATH=src pytest --cov=airfryer_rankings
PYTHONPATH=src python -m airfryer_rankings.run --mode hourly
```

For a complete deep refresh:

```bash
PYTHONPATH=src python -m airfryer_rankings.run --mode deep
```

## Scope and caveat

No crawler can prove complete coverage of every recipe on the public internet. Publishers can block crawlers, change markup, remove recipes, expose incomplete ratings, or use rating systems with different behavioral biases.

Recipe Intelligence therefore reports coverage, evidence confidence, source health, uncertainty, model robustness, benchmark quality, historical validation, and explicit data-quality gates alongside each production leaderboard. The objective is not to erase uncertainty; it is to make assumptions, evidence, failure modes, and model behavior measurable and reproducible.
