# Recipe Intelligence iOS MVP

Recipe Intelligence for iOS is the personal decision layer on top of the repository's evidence-driven recipe rankings. It targets iOS 17+ with SwiftUI and SwiftData.

## Open and run

Open `RecipeIntelligence.xcodeproj` in Xcode 16 or newer. Select the `RecipeIntelligence` scheme and an iPhone simulator. No signing team is required for simulator builds.

The production app reads the vertical catalog from:

`https://raw.githubusercontent.com/Chaseagle96/Recipe-Intelligence/main/api/verticals.json`

For deterministic UI tests, launch with `--ui-testing`; the app uses representative local fixture data and an in-memory SwiftData store.

## Architecture

- `Models.swift`: versioned Recipe Intelligence DTOs and product enums.
- `Networking.swift`: async/await Recipe Intelligence client with vertical discovery and paged feeds.
- `PersistenceModels.swift`: private local SwiftData entities for cache, profiles, households, saves, events, notes, reviews, cooking history, meal plans and shopping items.
- `RecommendationService.swift`: replaceable MVP recommendation interface plus a separate household-convergence interface.
- `ShoppingListService.swift`: ingredient parsing, conservative quantity merging and grocery categorization.
- `AppModel.swift`: main-actor orchestration and behavior-event capture.
- feature views: Discover, Saved/Elimination, Plan, Shopping, Reviews and Taste/Profile.

Remote Recipe Intelligence evidence is conceptually separate from private user-owned state. The app does not upload notes, reviews or behavioral data.

## Mobile backend contract

`api/verticals.json` enumerates available verticals. Each vertical points to its own `docs/api/manifest.json`, which declares the total ranked recipe count and ordered page files. Pages contain up to 100 recipes and expose:

- recipe and vertical IDs;
- title, publisher, author and canonical source URL;
- recipe image URL;
- factual ingredient lines;
- vertical rank, rating and rating count;
- evidence/rank confidence and provenance;
- instruction availability/count without republishing publisher instruction prose.

This is a serving projection only. It does not change Bayesian ranking, priors, calibration, dedupe or vertical isolation.

## Adding a vertical

Add the backend vertical normally, publish its paged mobile feed, then add one entry to `api/verticals.json`. The iOS vertical selector and paged client do not contain Air Fryer/Slow Cooker-specific branching.

## Persistence and learning events

The MVP records timestamped local events for impressions, opens, save/skip/Not Now swipes, undo, saves, plans, cooking/repeat cooking, favorites, reviews, notes, shopping-list generation, elimination rounds and source opens. Events are profile-scoped and retain the recipe and vertical IDs needed by a future recommendation service.

Multiple user profiles and a household entity exist from day one. Household recommendation is intentionally not faked: the MVP defines a separate convergence interface, while real per-person predicted enjoyment and household confidence are a future model milestone.

## Accessibility

Every swipe action has an explicit button equivalent. Recipe cards expose VoiceOver labels and custom actions, layouts use semantic Dynamic Type fonts, system colors and large controls, and swipe animations respect Reduce Motion.

## Known MVP limitations

- No account/cloud sync; personal data is local only.
- No public/social reviews or copied publisher comments.
- Publisher instruction prose is not republished; cooking directions open the canonical source page.
- Recommendation logic is a transparent quality/evidence/diversity baseline, not a trained Spotify-level model yet.
- Shopping normalization is intentionally conservative and does not convert incompatible units.
- Meal planning is one-week local planning without Calendar integration.
- Household convergence is architected but not learned yet.

## Validation

`.github/workflows/ios.yml` performs a real Xcode simulator build and executes unit plus UI tests on a macOS runner. Python CI independently validates the mobile serving projection and ensures Air Fryer/Slow Cooker ranking pipelines remain healthy.
