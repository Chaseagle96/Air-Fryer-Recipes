# Changelog

All notable ranking-engine and repository-governance changes are recorded here.

## Unreleased

### Added
- Independent **Slow Cooker** production vertical with its own source registry, discovery pattern, model configuration, storage policy, mutable state/history, evidence-label ledger, dedupe benchmark ledger, outputs, dashboard, and GitHub Actions refresh workflow.
- Slow Cooker discovery recognizes `slow cooker`, `slow-cooker`, `slow cooked`, `crockpot`, and `crock-pot` semantics without reusing the Air Fryer discovery regex.
- Shared runtime identity helpers allow reusable serving/analytical components to namespace vertical-specific artifacts while preserving Air Fryer compatibility.
- `VERTICALS.md` documents the isolation contract for current and future cooking-method verticals.

### Changed
- Repository/platform identity renamed from Air Fryer Recipe Rankings to **Recipe Intelligence**.
- Python distribution metadata renamed to `recipe-intelligence`; the internal `airfryer_rankings` namespace remains for 5.2.x compatibility.
- Primary GitHub Actions workflow, artifact labels, README badges, governance documentation, and generated dashboard now use the Recipe Intelligence identity.
- Air Fryer and Slow Cooker now share extraction/ranking/QA code but do not share mutable state, observations, priors, rank history, or serving snapshots.
- Crawler user-agent now identifies the broader Recipe Intelligence repository.

### Compatibility
- Existing Air Fryer raw evidence, state, ranking history, output filenames, Python import namespace, model version, and scoring behavior remain compatible.
- Air Fryer keeps its original discovery semantics; per-source `include_pattern` defaults to the existing Air Fryer regex unless a vertical overrides it.

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
