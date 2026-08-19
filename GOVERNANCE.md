# Repository Governance

## Change control

All substantive source, model, evidence, dedupe, CI, and publication-gate changes should be made through pull requests and validated by the repository workflows before merge.

Model identity is represented by:

- `model_version`: stable major model family used for backward compatibility.
- `model_semver`: semantic ranking-model release, for example `5.2.0`.
- `component_versions`: independently versioned ranking schema, evidence model, dedupe model, and uncertainty calibration components.

A change that can materially alter ranking order, uncertainty, evidence treatment, dedupe behavior, or eligibility should update `model_semver` and `CHANGELOG.md`.

## Publication SLOs

Operational thresholds are versioned in `config/slo.yaml`. Threshold changes require the same review and CI path as ranking changes. Warnings expose degraded but publishable runs. Failures stop production publication and preserve the previous serving state.

## Recommended GitHub repository settings

The following settings should be enabled in GitHub repository administration:

1. Protect `main`.
2. Require the Air Fryer Rankings validation workflow and CodeQL before merge.
3. Require branches to be up to date before merge.
4. Block force pushes and deletion of `main`.
5. Do not require an external human approval while the repository has a single maintainer.
6. Automatically delete merged feature branches.
7. Enable GitHub Pages with GitHub Actions as the deployment source.
8. Enable private vulnerability reporting.

These settings are deliberately documented here because repository-admin settings are not reproducible from ordinary source checkout alone.

## Release policy

`VERSION` is the repository release version. A merge to `main` that changes `VERSION` triggers the release workflow. The workflow validates that `VERSION` and `config/model.yaml` agree, then creates the corresponding `vX.Y.Z` GitHub tag and release if one does not already exist.

Release-worthy changes should update `CHANGELOG.md`.

## Historical integrity

Raw observation history is authoritative and immutable. Derived state, rankings, dashboards, spreadsheets, DuckDB databases, and Parquet archives may be regenerated from the authoritative evidence and versioned model configuration.
