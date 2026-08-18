from airfryer_rankings.core import RecipeRow, bayesian_rank, dedupe_current, ingredient_signature, merge_observations


def recipe(rid, title, source, rating, count, sig=""):
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
    )


def test_bayesian_rewards_volume_without_ignoring_rating():
    state = {"recipes": {}, "rank_history": [], "source_history": []}
    rows = [
        recipe("a", "Tiny Perfect", "x.com", 5.0, 2),
        recipe("b", "Huge Great", "x.com", 4.9, 5000),
        recipe("c", "Solid", "x.com", 4.7, 500),
    ]
    merge_observations(state, rows, "2026-08-18T20:00:00+00:00")
    ranked, method = bayesian_rank(state, stale_days=10000)
    assert ranked[0]["recipe_id"] == "b"
    assert method["volume_prior_m"] >= 50


def test_exact_cross_site_duplicate_combines_rating_volume():
    sig = ingredient_signature(["1 lb chicken", "1 tsp salt"])
    recipes = [
        {**recipe("a", "Air Fryer Chicken", "one.com", 4.8, 100, sig).__dict__, "last_seen_at": "2026-08-18T20:00:00+00:00"},
        {**recipe("b", "Air Fryer Chicken", "two.com", 5.0, 50, sig).__dict__, "last_seen_at": "2026-08-18T20:00:00+00:00"},
    ]
    deduped, count = dedupe_current(recipes)
    assert count == 1
    assert len(deduped) == 1
    assert deduped[0]["rating_count"] == 150
    assert round(deduped[0]["normalized_rating"], 4) == round((4.8 * 100 + 5.0 * 50) / 150, 4)


def test_ingredient_signature_is_order_independent():
    assert ingredient_signature(["Salt", "Chicken"]) == ingredient_signature(["chicken", "salt"])
