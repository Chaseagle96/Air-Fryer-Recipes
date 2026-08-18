from pathlib import Path

from airfryer_rankings.core import (
    RecipeRow,
    SourceConfig,
    bayesian_rank,
    categorize_recipe,
    dedupe_current,
    detect_anomalies,
    duplicate_similarity,
    extract_recipe_from_html,
    ingredient_signature,
    merge_observations,
    read_recent_records,
    select_refresh_targets,
    write_run_records,
)


def recipe(rid, title, source, rating, count, sig="", ingredients=()):
    return RecipeRow(
        rid,
        title,
        source,
        f"https://{source}/{rid}",
        rating,
        count,
        5,
        rating,
        "2026-08-18T20:00:00+00:00",
        ingredient_signature=sig,
        canonical_url=f"https://{source}/{rid}",
        ingredients=tuple(ingredients),
        evidence_confidence=0.9,
        evidence_status="schema_only",
        categories=categorize_recipe(title, ingredients),
    )


def test_bayesian_rewards_volume_without_ignoring_rating():
    state = {"recipes": {}, "rank_history": [], "source_history": [], "url_catalog": {}, "anomaly_history": []}
    rows = [
        recipe("a", "Tiny Perfect", "x.com", 5.0, 2),
        recipe("b", "Huge Great", "x.com", 4.9, 5000),
        recipe("c", "Solid", "x.com", 4.7, 500),
    ]
    merge_observations(state, rows, "2026-08-18T20:00:00+00:00")
    ranked, method = bayesian_rank(state, stale_days=10000)
    assert ranked[0]["recipe_id"] == "b"
    assert method["volume_prior_m"] >= 50
    assert "uncertainty_penalty" in ranked[0]


def test_cross_site_duplicate_does_not_double_count_review_population():
    ingredients = ["1 lb chicken breast", "1 tsp salt", "1 tbsp olive oil"]
    recipes = [
        {**recipe("a", "Air Fryer Chicken", "one.com", 4.8, 100, ingredient_signature(ingredients), ingredients).__dict__, "last_seen_at": "2026-08-18T20:00:00+00:00"},
        {**recipe("b", "Crispy Air Fryer Chicken", "two.com", 5.0, 50, ingredient_signature(["1 pound chicken breast", "salt", "olive oil"]), ["1 pound chicken breast", "salt", "olive oil"]).__dict__, "last_seen_at": "2026-08-18T20:00:00+00:00"},
    ]
    deduped, count, groups = dedupe_current(recipes, detailed=True)
    assert count == 1
    assert len(deduped) == 1
    assert deduped[0]["rating_count"] == 100
    assert len(groups) == 2
    assert deduped[0]["duplicate_confidence"] >= 0.88


def test_fuzzy_duplicate_similarity_uses_ingredients():
    a = recipe("a", "Air Fryer Chicken Breast", "one.com", 4.8, 100, ingredients=["1 lb chicken breast", "1 tbsp olive oil", "salt"]).__dict__
    b = recipe("b", "Crispy Air Fryer Chicken Breasts", "two.com", 4.9, 80, ingredients=["1 pound chicken breasts", "olive oil", "kosher salt"]).__dict__
    assert duplicate_similarity(a, b) >= 0.88


def test_ingredient_signature_is_order_independent():
    assert ingredient_signature(["Salt", "Chicken"]) == ingredient_signature(["chicken", "salt"])


def test_evidence_conflict_is_quarantined():
    html = '''
    <html><head><title>Air Fryer Test</title><link rel="canonical" href="https://x.com/test"></head><body>
    <span itemprop="ratingValue">4.1</span><span itemprop="ratingCount">100</span>
    <script type="application/ld+json">{
      "@type":"Recipe","name":"Air Fryer Test",
      "recipeIngredient":["chicken","salt"],
      "aggregateRating":{"ratingValue":"4.9","ratingCount":"100","bestRating":"5"}
    }</script></body></html>'''
    row, meta = extract_recipe_from_html(html, "https://x.com/test", "x.com", SourceConfig("x.com"))
    assert row is not None
    assert row.evidence_status == "conflict"
    assert row.evidence_confidence < 0.6
    state = {"recipes": {}, "rank_history": [], "source_history": [], "url_catalog": {}, "anomaly_history": []}
    merge_observations(state, [row], "2026-08-18T20:00:00+00:00")
    ranked, _ = bayesian_rank(state, stale_days=10000)
    assert ranked == []


def test_verified_dual_evidence_gets_high_confidence():
    html = '''
    <html><head><title>Air Fryer Test</title></head><body>
    <span itemprop="ratingValue">4.8</span><span itemprop="ratingCount">101</span>
    <script type="application/ld+json">{
      "@type":"Recipe","name":"Air Fryer Test",
      "recipeIngredient":["chicken","salt"],
      "aggregateRating":{"ratingValue":"4.8","ratingCount":"100","bestRating":"5"}
    }</script></body></html>'''
    row, _ = extract_recipe_from_html(html, "https://x.com/test", "x.com", SourceConfig("x.com"))
    assert row.evidence_status == "verified"
    assert row.evidence_confidence == 1.0


def test_publisher_bias_is_partially_pooled():
    state = {"recipes": {}, "rank_history": [], "source_history": [], "url_catalog": {}, "anomaly_history": []}
    rows = []
    for i in range(8):
        rows.append(recipe(f"a{i}", f"Air Fryer A {i}", "inflated.com", 4.95, 1000 + i))
        rows.append(recipe(f"b{i}", f"Air Fryer B {i}", "strict.com", 4.40, 1000 + i))
    merge_observations(state, rows, "2026-08-18T20:00:00+00:00")
    _, method = bayesian_rank(state, stale_days=10000)
    assert method["source_adjustments"]["inflated.com"]["bias"] > 0
    assert method["source_adjustments"]["strict.com"]["bias"] < 0


def test_hourly_selector_prioritizes_top_rank_and_new_urls():
    state = {
        "recipes": {"top": {"last_rank": 1, "rating_count": 1000, "previous_rating_count": 990}},
        "url_catalog": {
            "https://x.com/top": {"url": "https://x.com/top", "source": "x.com", "recipe_id": "top", "last_checked": "2026-08-18T19:00:00+00:00"},
            "https://x.com/old": {"url": "https://x.com/old", "source": "x.com", "last_checked": "2026-08-18T19:00:00+00:00"},
            "https://x.com/new": {"url": "https://x.com/new", "source": "x.com", "first_discovered": "2026-08-18T20:00:00+00:00"},
        },
    }
    targets = select_refresh_targets(state, [SourceConfig("x.com")], "hourly", hourly_limit=2)
    urls = [x["url"] for x in targets]
    assert "https://x.com/top" in urls
    assert "https://x.com/new" in urls


def test_anomaly_detection_flags_review_count_decrease():
    state = {"recipes": {}, "rank_history": [], "source_history": [], "url_catalog": {}, "anomaly_history": []}
    first = recipe("a", "Air Fryer Chicken", "x.com", 4.8, 100)
    merge_observations(state, [first], "2026-08-18T19:00:00+00:00")
    second = recipe("a", "Air Fryer Chicken", "x.com", 4.8, 90)
    merge_observations(state, [second], "2026-08-18T20:00:00+00:00")
    anomalies = detect_anomalies(state, [second], [], [], "2026-08-18T20:00:00+00:00")
    assert any(x["type"] == "review_count_decrease" for x in anomalies)


def test_immutable_run_observation_files(tmp_path: Path):
    records = [{"recipe_id": "a", "rating": 4.9, "rating_count": 100}]
    first = write_run_records(tmp_path, records, "2026-08-18T20:00:00+00:00")
    second = write_run_records(tmp_path, records, "2026-08-18T21:00:00+00:00")
    assert first != second
    assert Path(first).exists() and Path(second).exists()
    recent = read_recent_records(tmp_path, limit=10)
    assert len(recent) == 2


def test_category_classification_is_multilabel():
    cats = categorize_recipe("Air Fryer Chicken Breakfast Bites", ["eggs", "chicken breast"])
    assert "Chicken" in cats
    assert "Breakfast" in cats
    assert "Snacks" in cats


def test_jsonld_histogram_is_preserved_and_used():
    html = '''
    <html><head><title>Histogram Recipe</title></head><body>
    <script type="application/ld+json">{
      "@type":"Recipe","name":"Histogram Recipe",
      "recipeIngredient":["potato","salt"],
      "aggregateRating":{"ratingValue":"4.5","ratingCount":"100","bestRating":"5",
      "ratingHistogram":{"5":70,"4":20,"3":5,"2":3,"1":2}}
    }</script></body></html>'''
    row, _ = extract_recipe_from_html(html, "https://x.com/h", "x.com", SourceConfig("x.com"))
    assert row.rating_histogram["5"] == 70
    state = {"recipes": {}, "rank_history": [], "source_history": [], "url_catalog": {}, "anomaly_history": []}
    merge_observations(state, [row], "2026-08-18T20:00:00+00:00")
    ranked, _ = bayesian_rank(state, stale_days=10000)
    assert ranked[0]["uncertainty_penalty"] < 0.25


def test_review_velocity_is_exposed_per_day():
    state = {"recipes": {}, "rank_history": [], "source_history": [], "url_catalog": {}, "anomaly_history": []}
    first = recipe("a", "Air Fryer Chicken", "x.com", 4.8, 100)
    merge_observations(state, [first], "2026-08-18T19:00:00+00:00")
    second = recipe("a", "Air Fryer Chicken", "x.com", 4.8, 110)
    merge_observations(state, [second], "2026-08-18T20:00:00+00:00")
    ranked, _ = bayesian_rank(state, stale_days=10000)
    assert round(ranked[0]["review_velocity_per_day"], 6) == 240.0
