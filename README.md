# Air Fryer Recipe Rankings

An auditable, continuously refreshed leaderboard of highly rated air-fryer recipes from major public recipe publishers.

The project is designed to answer a harder question than “which recipe has the highest displayed star average?” It combines rating quality, rating volume, category mix, publisher-level rating tendencies, statistical uncertainty, evidence verification, duplicate detection, freshness, source reliability, and ranking robustness.

## What V4 does

### Incremental crawling instead of brute force

The crawler maintains a persistent URL catalog with discovery source, sitemap `lastmod`, first/last discovery time, last checked time, page hash, ETag, Last-Modified, last change time, HTTP state, and priority.

Refresh cadence:

- **Hourly:** re-check up to 100 high-priority URLs globally, favoring Top-100 recipes, new discoveries, modified pages, moving rating counts, and any recipe awaiting evidence migration.
- **Daily:** re-run discovery and revalidate the complete known catalog.
- **Weekly deep:** traverse a larger sitemap surface, refresh discovery pages, expand the known URL catalog, and revalidate the catalog.
- **Backfill:** force-refetch every legacy-evidence recipe without conditional HTTP shortcuts.
- **Pull requests:** run a bounded three-publisher live smoke crawl.

If V4 loads older state that still contains the former implicit 0.85 evidence-confidence assumption, it marks those rows `legacy_unverified`, lowers them to an explicit 0.60 confidence tier, prioritizes them for revalidation, and automatically turns the next normal hourly run into a backfill run until the old evidence has been re-extracted.

### Immutable evidence history plus DuckDB analytics

Every successful rating check is written as a new NDJSON record under:

`data/observations/YYYY/MM/DD/HHMMSSZ.ndjson`

Rank snapshots, coverage, and anomalies are also written as immutable NDJSON under `data/rankings/`, `data/coverage/`, and `data/anomalies/`.

**NDJSON remains the source of truth.** V4 additionally builds `output/air_fryer_analytics.duckdb` as a derived analytical cache. The DuckDB artifact contains current rankings, observation history, ranking history, source health/reliability, uncertainty calibration, robustness simulations, anomalies, and dedupe-benchmark results. It can always be rebuilt from the raw evidence layer.

### Evidence verification and evidence grades

Primary extraction uses Schema.org `Recipe` and `AggregateRating` JSON-LD. When visible/microdata rating evidence is also available, the two representations are cross-checked.

Evidence states include:

- `verified`: structured and visible evidence agree
- `schema_only`: valid AggregateRating was available but no independent visible value was found
- `visible_only`: only visible/microdata evidence was available
- `conflict`: structured and visible evidence materially disagree
- `legacy_unverified`: pre-V4 evidence awaiting forced revalidation

Conflicted or sub-threshold evidence is quarantined. Rankable rows receive an intuitive evidence grade (`A+` through `D`, with failing/conflicted evidence marked `F`) based on verification channel, confidence, rating volume, and freshness.

### Category-aware hierarchical Bayesian ranking

Raw star averages are not ranked directly.

1. Ratings are normalized to a five-star scale.
2. A global prior is estimated with square-root rating-count weighting.
3. Category baselines are partially pooled toward the global prior.
4. Publisher leniency/strictness is estimated from rating residuals after category expectations, reducing confounding from recipe mix.
5. Publisher bias is partially pooled and capped before adjustment.
6. Each recipe's adjusted rating is shrunk toward the global prior according to rating volume.
7. A calibrated uncertainty penalty is subtracted.
8. An evidence-quality penalty is subtracted when evidence confidence is below the preferred tier.

Conceptually:

`hierarchical_score = BayesianPosterior(category-aware source-adjusted rating) - calibrated uncertainty - evidence penalty`

This reduces the advantage enjoyed by publishers where nearly every recipe receives a very high average without assuming that publisher differences are entirely caused by rating generosity.

### Empirical uncertainty calibration

When a publisher exposes a usable rating histogram, observed star-distribution variance is used directly.

When no histogram is available, V4 groups historical rating observations into review-volume buckets:

- 0-24 ratings
- 25-99
- 100-499
- 500-1,999
- 2,000+

Each bucket remains on the conservative theoretical fallback until at least 30 real observation pairs exist. Once that threshold is reached, the fallback is automatically replaced by an empirical 95%-style penalty derived from observed rating changes in that volume regime.

### Ranking robustness laboratory

A single set of modeling constants should not create false precision. Every production ranking is therefore stress-tested across **36 deterministic nearby parameter combinations** spanning:

- publisher-bias cap
- evidence-penalty strength
- Bayesian prior strength
- uncertainty cap

The system reports:

- Spearman rank correlation for the Top 200
- Kendall rank correlation for the Top 100
- Top-10 overlap
- Top-50 overlap
- per-recipe rank standard deviation
- per-recipe likely rank range
- Top-10 and Top-50 frequency across simulations
- a 0-1 `rank_confidence` score

The dashboard and workbook expose these values so a recipe that is robustly #4 can be distinguished from one whose plausible position ranges from #3 to #35.

### Rank provenance

Every ranking row includes a human-readable explanation showing the components that produced the final score, including raw rating, category-aware publisher adjustment, Bayesian posterior, uncertainty penalty, evidence penalty, and final score.

### Longitudinal signals

Historical observations and ranking snapshots now support secondary metrics such as:

- 7-day review growth
- 30-day review growth
- 30-day rating trend
- review velocity per day
- all-time peak rank within retained history
- days observed in the Top 10
- days observed in the Top 50
- rank volatility

These are descriptive. Popularity growth does **not** directly boost the primary “best reviewed” ranking score.

### Fuzzy cross-site duplicate detection

Duplicate detection is intentionally conservative and uses several signals:

- canonical URL
- normalized title similarity
- normalized ingredient-token overlap
- instruction-token similarity
- 64-bit instruction SimHash
- author agreement
- image URL fingerprint as weak corroboration
- actual image-content perceptual hash for bounded ambiguous cases

Perceptual-image enrichment is limited to ambiguous duplicate candidates and capped at 20 image fetches per run so it does not double crawler traffic.

**Review counts from cross-site duplicates are not summed.** Syndicated pages can share a review population, so adding those counts would create false evidence.

### Formal dedupe benchmark

`data/benchmarks/dedupe_pairs.json` is a checked-in labeled benchmark containing true duplicates and hard negatives. Each run publishes:

- precision
- recall
- F1
- false-positive count
- false-negative count
- pair-level similarity and outcome

The benchmark is intentionally versioned and should grow over time with adjudicated real-world pairs from the live corpus.

### Source health instead of misleading “sources OK” counts

Hourly runs do not contact every publisher, so “not checked” must not be treated as failure. V4 separately reports:

- sources configured
- sources checked this run
- sources successful this run
- sources degraded this run
- sources healthy at last check
- sources checked within 24 hours
- sources checked within 7 days
- 24-hour corpus coverage freshness
- 7-day corpus coverage freshness

Per-publisher reliability also includes last-check timestamp, hours since last check, success rate, evidence confidence, pending legacy evidence, recent anomalies, and category-adjusted rating bias.

### Anomaly and QA detection

The pipeline flags conditions such as:

- rating counts decreasing
- explicit review velocity
- unusually large review-count jumps
- large rating changes
- structured/visible rating conflicts
- malformed rating scales
- duplicate canonical URLs
- recipes disappearing with 404/410 responses
- fetch/source degradation

## Outputs

### Repository data

- `output/top50.csv`
- `output/leaderboard.csv`
- `output/source_coverage.csv`
- `output/source_health.csv`
- `output/source_reliability.csv`
- `output/ranking_robustness.csv`
- `output/dedupe_benchmark.csv`
- `output/anomalies.csv`
- `output/summary.json`
- `data/state.json`
- `data/observations/...`
- `data/rankings/...`
- `data/coverage/...`
- `data/anomalies/...`
- `data/benchmarks/dedupe_pairs.json`

### Excel workbook

`output/air_fryer_rankings.xlsx` is uploaded as a GitHub Actions artifact and includes:

- Top 50
- All Rankings
- Rank Explainability
- Source Coverage
- Source Health
- Source Reliability
- Rating History
- Rating Trends with Top-10 rating-count growth chart
- Uncertainty Calibration
- Rank Robustness
- New Entrants
- Biggest Movers
- QA Anomalies
- Duplicate Groups
- Dedupe Benchmark
- Methodology
- Chicken
- Potatoes
- Vegetables
- Desserts
- Beef
- Pork
- Seafood
- Breakfast
- Snacks

### DuckDB analytical cache

`output/air_fryer_analytics.duckdb` is uploaded as a separate GitHub Actions artifact and contains queryable tables/views for current and historical research outputs. It is deliberately ignored by Git because it is a regenerable binary cache.

### Searchable web dashboard

Every production run builds a static site in `docs/` with:

- recipe/publisher search
- category filtering
- evidence-confidence filtering
- rank-confidence filtering
- hierarchical score
- evidence grade
- plausible rank range
- 7-day review growth
- review velocity
- ranking movement
- expandable “Why this rank?” provenance
- direct recipe links

## GitHub Actions

Workflow: `.github/workflows/hourly.yml`

Schedules:

- `17 * * * *` — hourly incremental refresh
- `43 8 * * *` — daily discovery and complete known-catalog refresh
- `13 9 * * 0` — weekly deep discovery and refresh

Manual runs support `hourly`, `daily`, `deep`, or `backfill` mode.

Pull requests automatically run tests plus a bounded live crawl against Pinch of Yum, Budget Bytes, and Skinnytaste without writing production state.

## Running locally

```bash
python -m pip install -r requirements.txt
PYTHONPATH=src pytest -q
PYTHONPATH=src python -m airfryer_rankings.run --mode hourly
```

For an explicit legacy-evidence refresh:

```bash
PYTHONPATH=src python -m airfryer_rankings.run --mode backfill
```

For a complete discovery refresh:

```bash
PYTHONPATH=src python -m airfryer_rankings.run --mode deep
```

## Ranking caveat

No crawler can literally prove complete coverage of every recipe on the public internet. Sites can block crawlers, omit ratings from machine-readable markup, change page structures, remove recipes, or expose only partial review evidence.

Accordingly, this project reports source coverage, extraction confidence, empirical/theoretical uncertainty, rank robustness, anomalies, freshness, and benchmark quality alongside rankings. The goal is not to pretend uncertainty does not exist; it is to make that uncertainty measurable, reproducible, and auditable.
