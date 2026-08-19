# Recipe Intelligence Governance

## Change control

All substantive source, model, evidence, dedupe, CI, vertical, and publication-gate changes should be made through pull requests and validated by the repository workflows before merge.

Model identity is represented by:

- `model_version`: stable major model family used for backward compatibility.
- `model_semver`: semantic ranking-model release, for example `5.2.0`.
- `component_versions`: independently versioned ranking schema, evidence model, dedupe model, and uncertainty calibration components.

A change that can materially alter ranking order, uncertainty, evidence treatment, dedupe behavior, or eligibility should update `model_semver` and `CHANGELOG.md`.

## Platform and vertical boundaries

Recipe Intelligence is the repository/platform identity. Air Fryer is the only production vertical in release 5.2.x.

New cooking-method verticals should reuse shared research infrastructure while keeping discovery configuration, eligibility rules, calibration context, and serving outputs isolated where the evidence requires it. A new vertical must not be silently mixed into an existing vertical's priors, longitudinal history, or publication baseline.

The existing `airfryer_rankings` Python namespace and Air Fryer output filenames are retained in 5.2.x as compatibility boundaries. Namespace/file migrations should happen only as part of a reviewed multi-vertical architecture change, not as cosmetic branding work.

## Publication SLOs

Operational thresholds are versioned in `config/slo.yaml`. Threshold changes require the same review and CI path as ranking changes. Warnings expose degraded but publishable runs. Failures stop production publication and preserve the previous serving state.

## Recommended GitHub repository settings

The following settings should be enabled in GitHub repository administration:

1. Protect `main`.
2. Require the Recipe Intelligence validation workflow and CodeQL before merge.
3. Require branches to be up to date before merge.
4. Block force pushes and deletion of `main`.
5. Do not require an external human approval while the repository has a single maintainer.
6. Automatically delete merged feature branches.
7. Enable GitHub Pages with GitHub Actions as the deployment source.
8. Enable private vulnerability reporting.

These settings are deliberately documented here because repository-admin settings are not reproducible from ordinary source checkout alone.

## Release policy

`VERSION` is the repository release version. A merge to `main` that changes `VERSION` triggers the release workflow. The workflow validates that `VERSION` and `config/model.yaml` agree, then creates the corresponding `vX.Y.Z` GitHub tag and release if one does not already exist.

Repository-only branding or documentation changes do not require a model-semantic-version bump when ranking behavior is unchanged. Release-worthy changes should still update `CHANGELOG.md`.

## Historical integrity

Raw observation history is authoritative and immutable. Derived state, rankings, dashboards, spreadsheets, DuckDB databases, and Parquet archives may be regenerated from the authoritative evidence and versioned model configuration.
