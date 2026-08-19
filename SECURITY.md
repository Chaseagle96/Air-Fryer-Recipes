# Security Policy

## Supported version

Security fixes are applied to the current `main` branch and the latest semantic repository release.

## Reporting a vulnerability

Do not include credentials, private tokens, or exploit secrets in a public issue. Use GitHub's private vulnerability reporting feature when it is available for this repository. If private reporting is unavailable, open a minimal public issue stating that you have a security concern and omit exploit details until a private channel is established.

## Supply-chain controls

The repository uses pinned GitHub Actions, dependency pinning, `pip-audit`, CycloneDX SBOM generation, Dependabot, CodeQL, Ruff, mypy, and branch-aware test coverage. Security-sensitive dependency or workflow changes should pass the same pull-request validation as ranking changes.

## Crawler safety

The crawler must respect configured request pacing, publisher failures, throttling signals, and explicit access restrictions. Changes that increase request concurrency or bypass publisher controls require explicit review.
