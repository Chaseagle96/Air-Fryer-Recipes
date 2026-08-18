# Air Fryer Recipe Rankings

An hourly, auditable leaderboard of the best-reviewed air-fryer recipes found across a broad set of public recipe publishers.

## What “best reviewed” means

The project does **not** rank recipes by raw star average alone. A 5.0-star recipe with 12 ratings should not automatically outrank a 4.9-star recipe with 8,000 ratings.

The ranking uses the Bayesian weighted-rating formula:

`WR = (v / (v + m)) * R + (m / (v + m)) * C`

Where:

- `R` = the recipe's normalized rating on a 5-star scale
- `v` = verified rating/review count
- `C` = a global prior, calculated as the square-root(review-count)-weighted mean rating across the current candidate pool
- `m` = volume prior, set to the larger of 50 reviews or the 60th-percentile review count

This shrinks low-volume ratings toward the global prior while allowing highly reviewed recipes to stand on their own evidence.

## Pipeline

1. Read a configurable set of recipe publishers from `config/sources.yaml`.
2. Discover sitemaps through each site's `robots.txt`, with `/sitemap.xml` fallback.
3. Identify likely air-fryer recipe URLs.
4. Respect robots rules and rate-limit page requests.
5. Extract Schema.org `Recipe` and `AggregateRating` JSON-LD.
6. Normalize ratings to 5 stars.
7. Preserve current observations and the latest seven days of hourly rank snapshots in `data/state.json`.
8. Deduplicate exact cross-site recipe matches using normalized title + ingredient signature.
9. Combine verified ratings for exact duplicate listings using review-count weighting.
10. Recompute the Bayesian leaderboard and rank movement.
11. Publish CSV/JSON results to the repository and an Excel workbook as a GitHub Actions artifact.

## Outputs

- `output/top50.csv` — current Top 50
- `output/leaderboard.csv` — all ranked recipes
- `output/summary.json` — methodology, Top 10, source coverage, run metrics
- `output/air_fryer_rankings.xlsx` — formatted workbook with Top 50, all rankings, source coverage, movers, and methodology sheets (uploaded as a workflow artifact rather than committed every hour)
- `data/state.json` — current recipe observations plus bounded history used to calculate movement

## Run locally

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
PYTHONPATH=src pytest -q
PYTHONPATH=src python -m airfryer_rankings.run
```

## Automation

GitHub Actions runs at minute 17 of every hour. The workflow can also be launched manually with **Run workflow**.

## Scope and data quality

This is designed to become an increasingly broad, evidence-based leaderboard, but no crawler can literally guarantee complete coverage of every recipe on the public internet. The system therefore reports source coverage and failures on every run and only ranks recipes for which a verifiable aggregate rating and rating/review count can be extracted.
