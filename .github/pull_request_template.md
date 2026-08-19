## Summary

Describe the change and why it is needed.

## Ranking impact

- [ ] No ranking/model behavior changes
- [ ] Ranking/model behavior changes are intentional and documented
- [ ] `config/model.yaml` semantic version is updated when model identity changes
- [ ] Golden-output differences were reviewed

## Data and evidence impact

- [ ] No raw observation history is rewritten
- [ ] Schema/contract changes are versioned
- [ ] Evidence-confidence or dedupe changes include benchmark/regression coverage
- [ ] Publication-gate/SLO changes are documented in `config/slo.yaml`

## Validation

- [ ] Ruff passes
- [ ] mypy passes
- [ ] pytest branch-coverage gate passes
- [ ] bounded live publisher smoke crawl passes
- [ ] CodeQL passes
- [ ] dependency audit reports no known vulnerabilities
- [ ] generated workbook and DuckDB artifacts were inspected when relevant

## Release discipline

- [ ] `CHANGELOG.md` updated for release-worthy changes
- [ ] `VERSION` updated when creating a new repository release
