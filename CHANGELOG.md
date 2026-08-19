# Changelog

All notable ranking-engine and repository-governance changes are recorded here.

## 5.2.0 - 2026-08-18

### Added
- Semantic `model_semver` plus component-level model versions.
- Versioned publication SLO policy in `config/slo.yaml`.
- Degraded crawl, extraction, DOM-change, anomaly, stale-source, throttling, and rank-churn warnings.
- Catastrophic crawl/extraction and markup-change publication failures.
- Repository release automation, governance documentation, CODEOWNERS, security policy, and pull-request checklist.

### Changed
- Publication-gate model identity now considers semantic model version as well as the major model family.
- Ranking snapshots and `output/summary.json` record semantic model identity.

## 5.1.0 - 2026-08-18

### Fixed
- Prevented hourly repeated observations from falsely activating empirical uncertainty.
- Required review growth, 24-hour pair spacing, 30 informative pairs, 10 recipes, and 21 days of temporal diversity before empirical uncertainty can activate.
- Retained a count-sensitive conservative uncertainty floor after empirical calibration.

## 5.0.0 - 2026-08-18

### Added
- Typed and versioned raw, clean, model, and serving contracts.
- Ranking-component decomposition and historical predictive backtesting.
- Structural publisher monitoring and real-page regression fixtures.
- Evidence-confidence calibration framework.
- Dedupe benchmark governance and ambiguity labeling queue.
- Observability metrics and fail-closed publication gate.
- Golden, property-based, fixture, and regression tests.
- Ruff, mypy, branch coverage, dependency audit, SBOM, CodeQL, Dependabot, DuckDB, and Parquet archival support.
