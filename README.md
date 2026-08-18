# Air Fryer Recipe Rankings

An auditable, continuously refreshed leaderboard of highly rated air-fryer recipes from major public recipe publishers.

The project is designed to answer a harder question than “which recipe has the highest displayed star average?” It combines rating quality, rating volume, publisher-level rating tendencies, uncertainty, evidence verification, duplicate detection, freshness, and source reliability.

## What V3 does

### Incremental crawling instead of brute force

The crawler maintains a persistent URL catalog with discovery source, sitemap `lastmod`, first/last discovery time, last checked time, page hash, ETag, Last-Modified, last change time, HTTP state, and priority.

Refresh cadence:

- **Hourly:** re-check up to 100 high-priority URLs globally, favoring Top-100 recipes, new discoveries, recently modified pages, and recipes whose rating counts are moving.
- **Daily:** re-run discovery and revalidate the complete known catalog.
- **Weekly deep:** traverse a larger sitemap surface, refresh discovery pages, expand the known URL catalog, and revalidate the catalog.
- **Pull requests:** run a bounded three-publisher live smoke crawl.

Conditional requests use ETag and Last-Modified when publishers provide them.

### Immutable rating-observation history

Every successful rating check is written as a new NDJSON record under:

`data/observations/YYYY/MM/DD/HHMMSSZ.ndjson`

Records include recipe ID, timestamp, publisher, URL, rating, rating count, evidence confidence, extraction method, page hash, and fetch status. New files are appended rather than rewriting old observation logs, so historical evidence remains reconstructable without quadratic Git history growth.

Anomalies are recorded separately under `data/anomalies/`.

### Evidence verification

Primary extraction uses Schema.org `Recipe` and `AggregateRating` JSON-LD. When visible/microdata rating evidence is also available, the two representations are cross-checked.

Evidence states include:

- `verified`: structured and visible evidence agree
- `schema_only`: valid AggregateRating was available but no independent visible value was found
- `visible_only`: only visible/microdata evidence was available
- `conflict`: structured and visible evidence materially disagree

Conflicted or low-confidence recipes are retained for QA but quarantined from ranking.

The crawler records page hashes, canonical URLs, extraction method, and evidence confidence so a ranking can be traced back to its evidence state.

### Hierarchical Bayesian ranking

Raw star averages are not ranked directly.

1. Ratings are normalized to a five-star scale.
2. A global prior is estimated with square-root rating-count weighting.
3. Each publisher receives a partially pooled mean rating estimate.
4. Publisher rating bias is estimated relative to the global prior.
5. Each recipe's rating is adjusted for that estimated publisher tendency.
6. The adjusted rating is shrunk toward the global prior according to rating volume.
7. A conservative uncertainty penalty is subtracted.

Conceptually:

`hierarchical_score = BayesianPosterior(source-adjusted rating) - uncertainty penalty`

When a publisher exposes a usable rating histogram in structured data, observed star-distribution variance is used for the uncertainty calculation. Otherwise the system uses a conservative bounded-rating variance assumption.

This reduces the advantage enjoyed by publishers where nearly every recipe receives a very high average and penalizes statistically fragile recipes with very few ratings.

### Fuzzy cross-site duplicate detection

Duplicate detection is intentionally conservative and uses several signals:

- canonical URL
- normalized title similarity
- normalized ingredient-token overlap
- instruction similarity
- author agreement
- image-URL fingerprint as a weak corroborating signal

A high-confidence fuzzy cluster creates a duplicate group with provenance for every source listing.

**Review counts from cross-site duplicates are not summed.** Syndicated pages can share a review population, so adding those counts would create false evidence. The highest-volume credible listing is used as the representative while all source evidence remains visible in the duplicate audit output.

### Anomaly and QA detection

The pipeline flags conditions such as:

- rating counts decreasing
- unusually large review-count jumps
- large rating changes
- structured/visible rating conflicts
- malformed rating scales
- duplicate canonical URLs
- recipes disappearing with 404/410 responses
- fetch/source degradation

These appear in CSV, workbook, history, and dashboard data.

### Discovery beyond URL-name matching

Sitemaps remain the largest discovery surface, but V3 also supports curated category/search/discovery pages. Links found on those pages can enter the URL catalog even when the recipe slug itself does not contain “air fryer.”

The registry currently includes **40 publishers**, including the original broad publisher set plus Serious Eats, The Kitchn, Food & Wine, Ambitious Kitchen, Eating Bird Food, Wholesome Yum, Dinner at the Zoo, Diethood, Two Peas & Their Pod, Everyday Family Cooking, Air Frying Foodie, Plated Cravings, Rachel Cooks, and Mel's Kitchen Cafe.

External discovery is intentionally seed-driven rather than scraping general-purpose search engines without an approved search API. New search-engine findings can be added as publisher discovery URLs without changing the crawler.

## Outputs

### Repository data

- `output/top50.csv`
- `output/leaderboard.csv`
- `output/source_coverage.csv`
- `output/source_reliability.csv`
- `output/anomalies.csv`
- `output/summary.json`
- `data/state.json`
- `data/observations/...`
- `data/anomalies/...`

### Excel workbook

`output/air_fryer_rankings.xlsx` is uploaded as a GitHub Actions artifact and includes:

- Top 50
- All Rankings
- Source Coverage
- Source Reliability
- Rating History
- New Entrants
- Biggest Movers
- QA Anomalies
- Duplicate Groups
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

### Searchable web dashboard

Every production run builds a static site in `docs/` with:

- searchable recipe/publisher table
- category filtering
- evidence-confidence filtering
- hierarchical score
- raw stars and rating count
- ranking movement
- direct recipe links
- methodology metadata

The workflow also attempts deployment through GitHub Pages using `actions/deploy-pages`. Page deployment is non-blocking so a Pages configuration problem cannot break the ranking pipeline itself.

## GitHub Actions

Workflow: `.github/workflows/hourly.yml`

Schedules:

- `17 * * * *` — hourly incremental refresh
- `43 8 * * *` — daily discovery and complete known-catalog refresh
- `13 9 * * 0` — weekly deep discovery and refresh

Manual runs support `hourly`, `daily`, or `deep` mode.

Pull requests automatically run tests plus a bounded live crawl against Pinch of Yum, Budget Bytes, and Skinnytaste without writing production state.

## Running locally

```bash
python -m pip install -r requirements.txt
PYTHONPATH=src pytest -q
PYTHONPATH=src python -m airfryer_rankings.run --mode hourly
```

For a complete discovery refresh:

```bash
PYTHONPATH=src python -m airfryer_rankings.run --mode deep
```

## Ranking caveat

No crawler can literally prove complete coverage of every recipe on the public internet. Sites can block crawlers, omit ratings from machine-readable markup, change page structures, remove recipes, or expose only partial review evidence.

Accordingly, this project reports source coverage, extraction confidence, anomalies, and freshness alongside rankings. The goal is not to pretend uncertainty does not exist; it is to make that uncertainty measurable and auditable.
