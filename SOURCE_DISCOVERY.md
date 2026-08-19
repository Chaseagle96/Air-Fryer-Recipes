# Autonomous Source Discovery and Qualification

Recipe Intelligence is designed to expand beyond a permanently fixed publisher panel without treating search visibility as trust. Internet-wide discovery and production admission are separate systems.

## Architecture

```text
              PUBLIC WEB
                   |
                   v
        +---------------------+
        | Candidate Discovery |
        +----------+----------+
                   |
                   v
           Candidate Registry
                   |
                   v
        +---------------------+
        | Qualification Gate  |
        +----------+----------+
                   |
          +--------+--------+
          |                 |
       Reject           Quarantine
                            |
                            v
                        Promote
                            |
             +--------------+--------------+
             |                             |
        Manual/Pinned               Auto-Promoted
             |                             |
             +--------------+--------------+
                            v
                    Effective Allowlist
                            |
                            v
                   URL/Sitemap Discovery
                            |
                            v
                    Recipe Extraction
                            |
                            v
                    Evidence Validation
                            |
                            v
                    Bayesian Ranking
```

The checked-in source YAML files remain the maintainer-owned base layer. Machine-discovered sources live in independent vertical-local registries:

- Air Fryer: `data/source_registry.json`
- Slow Cooker: `verticals/slow_cooker/data/source_registry.json`

`load_sources()` synthesizes the effective allowlist as `base/pinned + eligible auto-promoted`. Machine automation never needs to rewrite the curated YAML to add or suspend an automatically discovered publisher.

## Candidate discovery

The shared source-expansion engine supports several independent candidate mechanisms:

1. **Brave Search API**, when `BRAVE_SEARCH_API_KEY` is configured.
2. **Google Custom Search JSON API**, when `GOOGLE_CSE_API_KEY` and `GOOGLE_CSE_ID` are configured.
3. **Trusted outbound-link discovery**, which inspects a bounded set of existing publisher discovery/recipe pages for cooking-method-relevant links to external publishers.
4. **Cross-vertical seeding**, which asks every other vertical to evaluate domains observed elsewhere without transferring vertical qualification.
5. **Bootstrap seed files**, used only for explicitly bounded initial research runs. A seed creates a candidate; it does not approve the candidate.

Search-provider failure is soft. Missing keys, provider outages, or result errors are recorded in source-expansion diagnostics and do not affect hourly ranking refreshes.

Query families are generated deterministically from the vertical's method terms plus proteins, cuisines, meal types, recipe categories, and ingredients in `config/source_discovery.yaml`. Budgets bound search queries, results, candidate domains, pages per domain, total qualification pages, sitemap documents, outbound pages, promotions, and wall-clock discovery time.

The public Common Crawl CDX index is not used as a broad keyword search engine. Its URL index remains a possible future provider when paired with an appropriate bulk-query/index-processing implementation rather than high-volume CDX filtering.

## Domain normalization and network safety

Dynamic domains are untrusted input. `source_security.py`:

- accepts only HTTP and HTTPS;
- rejects credentials and non-standard ports;
- rejects IP literals as publisher identities;
- strips only a leading `www.` alias and preserves meaningful publisher subdomains;
- rejects obvious social, search, shopping, affiliate/shortener, aggregator, ad, CDN, image, analytics, auth, and generic-hosting candidates;
- resolves candidate hosts before requests and rejects loopback, private, link-local, reserved/non-global, and known metadata targets;
- follows redirects manually and revalidates every redirect destination;
- applies guarded network fetches throughout robots, sitemap, category discovery, qualification, catalog synchronization, and production crawling for machine-discovered sources.

Pinned/manual sources preserve the pre-existing networking behavior, limiting regression risk while all new autonomous input is guarded. Historical non-publisher candidates are audit-retired without deleting their discovery provenance.

## Lifecycle

Automatic candidates use auditable states:

```text
DISCOVERED -> CANDIDATE -> QUARANTINED -> QUALIFIED -> PROMOTED -> ACTIVE
                                                        |
                                                        v
                                                   DEGRADED
                                                        |
                                                        v
                                                   SUSPENDED
                                                        |
                                                repeated healthy
                                                 requalification
                                                        |
                                                        v
                                                     ACTIVE
```

`REJECTED` and `BLOCKED` are terminal/cooldown paths for failed gates and explicit maintainer decisions. Historical candidate and recipe evidence is never deleted by a state transition.

A newly discovered domain never enters production directly. Normal automatic promotion requires two qualifying evaluations. A weekly deep run can fast-track an exceptionally strong source only when it clears the higher score/sample/reliability/relevance requirements configured in the gate.

## Source qualification gate v2

`source_gate_version: 2` is the current decision model. Every new evaluation and transition records that version, while historical v1 audit events retain the exact gate version and metrics that justified their original decisions.

Gate v2 corrects an important distinction in the original bootstrap model. The production ranking extractor intentionally emits a ranking row only when a recipe has usable rating/review evidence. Therefore, a recipe page without public ratings is not an extractor failure. V2 separates:

- **recipe structure/extractability**, meaning the publisher exposes substantive recipe data Recipe Intelligence can parse;
- **ranking-evidence coverage**, meaning the share of sampled recipes currently carrying usable rating/review evidence;
- **conditional extraction success**, meaning the production ranking extractor's success rate only among pages where ranking evidence is present.

This prevents a legitimate editorial or test-kitchen publisher from being penalized merely for omitting public star ratings, while still detecting genuine extractor incompatibility on publishers that do expose ranking evidence.

### Hard gates

A domain cannot compensate for a hard integrity failure with a high weighted score. Gate v2 checks, among other things:

- robots/technical availability and fetch yield;
- minimum bounded sample size;
- a meaningful vertical recipe body;
- Recipe structured-content yield;
- vertical relevance;
- substantive ingredients/instructions;
- ranking-extractor compatibility when at least three sampled pages contain ranking evidence;
- external-canonical/mirror behavior;
- extreme within-source duplicate content;
- crawler-trap URL patterns;
- repeated visible/structured rating conflicts.

The default conditional extraction hard gate is 60% once at least three evidence-bearing sample pages exist. Sparse or absent rating evidence does not trigger that gate. Temporary evidence shortfalls such as an unavailable robots endpoint, too few sampled pages, or transient fetch failure remain quarantined instead of becoming permanent rejection from one run.

### Weighted score

The configurable v2 weights are:

| Component | Weight |
|---|---:|
| Vertical relevance / usable yield | 20% |
| Recipe structure / extraction reliability | 20% |
| Editorial provenance | 15% |
| Crawl stability | 15% |
| Rating/review integrity | 10% |
| Unique contribution vs current corpus | 10% |
| Freshness | 5% |
| General source-quality signals | 5% |

Within the extraction-reliability component, conditional production-extractor success is included when ranking evidence exists. When no ranking evidence is present, that sub-weight is redistributed across recipe structure, field completeness, and substantive-content signals instead of treating missing ratings as failure.

The default qualification threshold remains 74/100. Normal promotion requires two independent qualifying attempts. A deep fast-track requires at least 88/100 plus a larger sample and stricter fetch/structure/relevance conditions.

**Public star ratings are not a prerequisite for source legitimacy.** A publisher with no public rating system receives neutral rating-integrity treatment at the source gate. Individual recipes still need the normal Recipe Intelligence evidence required by the Bayesian ranking system, so source trust cannot manufacture recipe-rating evidence.

## Qualification evidence

The bounded evaluator samples multiple vertical-relevant URLs and records:

- candidate vertical URL count;
- pages sampled/fetched;
- Recipe JSON-LD recognition;
- ranking-evidence page count and coverage;
- ranking-row yield;
- conditional ranking-extractor success;
- ingredient/instruction substance;
- yield/time/author/publisher/date completeness;
- vertical relevance ratio;
- visible/structured rating agreement where ratings exist;
- canonical ownership;
- crawl-trap indicators;
- within-source duplicate ratio;
- approximate novelty against the current vertical corpus using the existing Recipe Intelligence duplicate-similarity model;
- publication freshness when dates are available.

This makes the answer to “why is this domain trusted?” reproducible from persisted evidence instead of relying on search rank or marketing language.

## Promotion and production crawling

When a candidate is promoted, its machine-owned `crawl_config` contains its relevant sitemap/discovery entry points, inclusion pattern, crawl delay, and URL cap. It immediately becomes part of the effective allowlist. After a successful production source-expansion run, `.github/workflows/source-catalog-sync.yml` invokes `airfryer_rankings.source_catalog_sync` to seed every production-eligible discovered publisher into that vertical's persistent URL catalog through the existing `discover_source_urls()` path.

Trust decisions and ranking-state mutation remain isolated. Source expansion owns qualification and the machine registry; catalog sync mutates only `url_catalog`, reuses robots and dynamic-source SSRF protections, validates that every effective auto-source has persistent catalog coverage, and refuses to commit if that invariant is not satisfied. It does not rewrite recipes, observations, priors, rankings, or historical evidence.

All recipes from an auto source still flow through the existing extraction, evidence validation, anomaly detection, dedupe, Bayesian ranking, robustness, and publication gates. Source promotion changes the universe that Recipe Intelligence is allowed to research; it does not bypass recipe-level quality controls.

## Continuous monitoring and hysteresis

Promoted sources reuse normal production source-history observations.

Default lifecycle hysteresis is:

- three consecutive degraded checks: `ACTIVE -> DEGRADED`;
- five consecutive degraded checks: `DEGRADED -> SUSPENDED`;
- two consecutive healthy checks: `DEGRADED -> ACTIVE`;
- suspended sources are reconsidered during deep evaluation and require repeated healthy requalification to recover.

Pinned sources are never silently auto-suspended. Degradation is surfaced as a maintainer warning instead.

## Cross-vertical behavior

Candidate-domain awareness is shared, but vertical trust is not. If Air Fryer discovers a promising domain, Slow Cooker receives it as a candidate and independently tests whether it has a meaningful Slow Cooker recipe body. Technical compatibility can therefore be learned efficiently without allowing one vertical's relevance to contaminate another vertical's population, priors, or state.

## Cadence and failure isolation

`.github/workflows/source-expansion.yml` and `.github/workflows/source-catalog-sync.yml` are separate from the high-frequency ranking workflows.

- Hourly ranking: approved sources and the existing URL catalog only. No internet-wide search.
- Daily source expansion: bounded query/outbound discovery and a small qualification queue.
- Weekly deep source expansion: broader query family, larger samples, cross-vertical re-evaluation, suspended-source recovery, and more promotion capacity.
- Post-expansion catalog sync: after a successful production source-expansion run, seed/refresh auto-promoted publishers in the persistent URL catalogs and persist synchronization diagnostics.

A source-expansion or catalog-sync workflow failure does **not** prevent Air Fryer or Slow Cooker hourly refreshes from operating against their last approved effective allowlists and catalogs.

Production source expansion runs through `airfryer_rankings.source_expansion_v2`, which installs gate-v2 scoring and metrics over the shared discovery, security, registry, lifecycle, and persistence engine. This keeps the decision model explicitly versioned while preserving all historical v1 audit evidence.

## Observability and auditability

Each vertical writes `output/source_expansion.json`; the aggregate run writes `output/source_expansion_all.json`. Metrics include:

- candidate domains discovered/new/evaluated/rejected/quarantined/promoted;
- active/degraded/suspended candidate counts;
- promotion rate;
- median source quality score;
- qualification pages fetched;
- qualification conditional extraction success rate;
- qualification ranking-row yield;
- manual, auto, and effective source counts;
- URL catalog count and post-promotion URL additions;
- per-source catalog synchronization evidence;
- provider availability/errors;
- pinned-source degradation warnings.

Every state transition is appended to the registry audit and also emitted as immutable vertical-local NDJSON under `data/source_events/` or the corresponding vertical tree. Records include previous/new state, reason, metrics, thresholds, timestamp, vertical, and source-gate version.

## Manual overrides

Use the administrative CLI with an explicit reason:

```bash
PYTHONPATH=src python scripts/source_registry_admin.py air_fryer approve example.com --reason "maintainer review"
PYTHONPATH=src python scripts/source_registry_admin.py air_fryer reject example.com --reason "scraped mirror"
PYTHONPATH=src python scripts/source_registry_admin.py slow_cooker block example.com --reason "do not rediscover"
PYTHONPATH=src python scripts/source_registry_admin.py slow_cooker pin example.com --reason "maintainer-trusted publisher"
PYTHONPATH=src python scripts/source_registry_admin.py air_fryer suspend example.com --reason "manual incident response"
PYTHONPATH=src python scripts/source_registry_admin.py air_fryer restore example.com --reason "publisher repaired"
```

A block/reject override can prevent repetitive rediscovery. A manual YAML source remains pinned regardless of a conflicting machine record.

## Adding another vertical

A new vertical does not copy the source-expansion engine. Add one entry under `verticals:` in `config/source_discovery.yaml` specifying:

- the base source YAML;
- vertical state/registry/output/event paths;
- the method-specific inclusion regex;
- query terms and diversification dimensions.

Use the normal vertical working-directory/state isolation pattern. The shared discovery, qualification, security, registry, lifecycle, catalog synchronization, and observability implementation then applies unchanged.
