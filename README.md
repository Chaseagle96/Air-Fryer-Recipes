# Air Fryer Recipe Rankings

[![Air Fryer Rankings](https://github.com/Chaseagle96/Air-Fryer-Recipes/actions/workflows/hourly.yml/badge.svg)](https://github.com/Chaseagle96/Air-Fryer-Recipes/actions/workflows/hourly.yml)
[![CodeQL](https://github.com/Chaseagle96/Air-Fryer-Recipes/actions/workflows/codeql.yml/badge.svg)](https://github.com/Chaseagle96/Air-Fryer-Recipes/actions/workflows/codeql.yml)
[![Release](https://img.shields.io/github/v/release/Chaseagle96/Air-Fryer-Recipes)](https://github.com/Chaseagle96/Air-Fryer-Recipes/releases/latest)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**Current release: 5.2.0**

An auditable, continuously refreshed leaderboard of highly rated air-fryer recipes from public recipe publishers.

The project does not simply sort displayed star averages. It combines rating quality and volume, category-aware publisher normalization, Bayesian shrinkage, uncertainty, extraction evidence, duplicate detection, freshness, longitudinal behavior, source health, and ranking robustness.

## V5 architecture

V5 treats the repository as a research and production data pipeline with four explicit contracts:

1. **Raw evidence**: immutable observations under `data/observations/`. This is the longitudinal source of truth.
2. **Clean state**: validated current recipe evidence in `data/state.json`. Individual clean recipe records are schema-versioned independently from the state envelope.
3. **Model outputs**: immutable ranking snapshots under `data/rankings/`, generated from a frozen versioned model configuration.
4. **Serving outputs**: CSV, Excel, DuckDB, JSON, and GitHub Pages artifacts under `output/` and `docs/`.

Derived layers can be regenerated. Raw observation history is never rewritten to make it agree with a later model.

### Ranking model

The active model is versioned in `config/model.yaml`. Production parameters never self-modify.

For each eligible recipe, V5:

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

- Top-200 Spearman correlation
- Top-100 Kendall correlation
- Top-10 and Top-50 overlap
- per-recipe rank standard deviation
- likely rank range
- Top-10 and Top-50 frequency
- `rank_confidence` from 0 to 1

A deterministic golden-ranking fixture ensures scoring changes create a reviewable CI diff rather than silent rank drift.

### Historical predictive backtesting

V5 can evaluate ranking models against later high-volume evidence rather than judging parameters only by plausibility.

Daily/deep runs can test frozen candidate configurations over 30-, 60-, and 90-day horizons and report:

- future-quality rank correlation
- posterior mean absolute error
- final-score mean absolute error
- future Top-10 overlap

Backtesting remains disabled until enough longitudinal history exists. `config/model.yaml` requires minimum history/windows/recipe coverage, and `automatic_parameter_promotion` is explicitly false. A recommended configuration is advisory until changed through a reviewed model-version update.

### Time-aware diagnostics

Observation history supports:

- 7-day and 30-day review growth
- 30-day rating slope
- 30-day review-count slope
- 7-day velocity
- 14-day review acceleration
- page-change count and last material page change
- recent rating change-point detection
- peak rank
- days in Top 10 and Top 50
- rank volatility

These signals aid interpretation and anomaly detection without turning virality into quality.

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

Every fetched page records:

- page content hash
- structural DOM fingerprint
- JSON-LD schema signature
- visible rating-evidence shape

Changes to publisher markup generate QA/observability events even when HTTP requests still succeed.

### Reviewed real-page fixtures

`tests/fixtures/real_pages/` contains sanitized structural snapshots tied to real publisher pages. They preserve only the fields necessary to test extraction behavior.

Weekly deep runs can capture candidate fixtures from configured publishers into an Actions artifact. Candidates never overwrite checked-in fixtures automatically; promotion requires a reviewed code change so broken publisher markup cannot redefine the regression test.

### Evidence-confidence calibration

`data/benchmarks/evidence_labels.json` contains reviewed fixture expectations. V5 estimates extraction correctness and Wilson intervals by evidence class, but empirical confidence replacement does not activate until a class has at least the configured minimum reviewed sample size. Small seed samples therefore cannot masquerade as calibrated probabilities.

## Duplicate detection

Cross-site dedupe is deliberately precision-oriented. Signals include:

- canonical URL
- normalized title similarity
- normalized ingredient overlap
- instruction-token overlap
- instruction SimHash
- author agreement
- image URL fingerprint
- bounded actual image-content perceptual hashing for ambiguous candidates

Cross-site review counts are **never summed** because syndicated pages may share a review population.

### Dedupe benchmark

`data/benchmarks/dedupe_pairs.json` is a versioned adjudicated validation set. V5 reports:

- precision, recall, and F1
- TP/FP/TN/FN
- positive/negative similarity distributions
- threshold precision/recall curve
- metrics by labeled pair type
- pair-level outcomes

CI currently requires at least 95% precision and 90% recall. The benchmark policy targets at least 500 manually adjudicated pairs. `output/dedupe_label_queue.csv` surfaces ambiguous real-corpus candidates nearest the production threshold for review.

## Observability and fail-closed publishing

Source health distinguishes “not checked” from “failed.” Pipeline metrics include:

- crawl/extraction success
- ranking eligibility
- evidence-conflict rate
- robots denials
- HTTP 403/429 counts
- mean/p95 fetch time
- source freshness
- structural publisher changes
- legacy-evidence backlog
- anomaly volume

Before a production result is committed, a publication gate checks for catastrophic regressions such as:

- empty leaderboard
- major corpus-size collapse
- inability to produce a Top 50
- catastrophic evidence-conflict rate
- unexplained Top-50 collapse without a model-version change
- implausible dedupe explosion

If the gate fails, the workflow fails before state is persisted or public output is committed. Diagnostic artifacts are still uploaded so the failed candidate run can be inspected while the prior public leaderboard remains intact.

## Historical storage

`config/storage.yaml` defines the storage contract.

- Git-backed NDJSON remains authoritative today.
- `output/air_fryer_analytics.duckdb` is a regenerable analytical cache.
- Weekly deep runs can generate a compressed Parquet history archive artifact.
- Storage health reports NDJSON records/bytes and recommends archival migration once configured thresholds are crossed.
- External object-storage upload is disabled unless explicitly configured in the environment and policy.

This gives the project a migration path away from unbounded Git history without prematurely introducing external infrastructure.

## Outputs

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

The workbook includes the Top 50, all rankings, rank explainability, source coverage/health/reliability, rating history/trends, time signals, uncertainty calibration, evidence calibration, evidence labels, robustness simulations, historical backtests, hyperparameter evaluation, pipeline metrics, publication gate, storage health, data contracts, movers, entrants, QA anomalies, duplicate groups, dedupe benchmark/label queue, methodology, and category leaderboards.

### Analytical artifacts

- `air_fryer_analytics.duckdb`: queryable current/history/research tables and Top-10/Top-50 views
- `history_archive.parquet`: compressed deep-run historical archive when generated
- `sbom.json`: CycloneDX software bill of materials
- `fixture-candidates`: sanitized publisher regression-fixture candidates from deep runs

## Continuous integration and supply-chain controls

The primary workflow runs:

1. pinned dependency installation;
2. vulnerability audit and CycloneDX SBOM generation;
3. Ruff linting;
4. mypy static analysis;
5. pytest with branch coverage gate;
6. bounded live three-publisher PR crawl;
7. Excel/DuckDB generation;
8. publication-gate evaluation.

GitHub Actions are pinned to exact commit SHAs. CodeQL runs independently. Dependabot monitors both Python dependencies and Actions references.

The test suite combines deterministic unit/regression tests, reviewed real-page fixture tests, Hypothesis property tests, benchmark quality floors, and golden model-output tests.

## Refresh cadence

- `17 * * * *`: hourly incremental refresh
- `43 8 * * *`: daily discovery/full-known-catalog refresh plus backtest evaluation
- `13 9 * * 0`: weekly deep discovery/refresh, storage archive and candidate fixture capture
- manual: `hourly`, `daily`, `deep`, or `backfill`
- pull requests: static/security/test gates plus bounded live smoke crawl without production writes

## Running locally

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

For a legacy-evidence revalidation pass:

```bash
PYTHONPATH=src python -m airfryer_rankings.run --mode backfill
```

## Scope and caveat

No crawler can prove complete coverage of every air-fryer recipe on the public internet. Publishers can block crawlers, change markup, remove recipes, expose incomplete ratings, or use rating systems with different behavioral biases.

The project therefore reports coverage, evidence confidence, source health, uncertainty, model robustness, benchmark quality, historical validation, and explicit data-quality gates alongside the leaderboard. The objective is not to erase uncertainty; it is to make the assumptions, evidence, failure modes, and model behavior measurable and reproducible.
