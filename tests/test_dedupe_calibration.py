from airfryer_rankings.benchmarks import evaluate_dedupe_benchmark
from airfryer_rankings.dedupe import DEDUPE_THRESHOLD, duplicate_similarity


def test_production_dedupe_threshold_is_benchmark_calibrated():
    summary, _ = evaluate_dedupe_benchmark("data/benchmarks/dedupe_pairs.json")
    assert DEDUPE_THRESHOLD == 0.80
    assert summary["threshold"] == DEDUPE_THRESHOLD
    assert summary["precision"] >= 0.95
    assert summary["recall"] >= 0.90
    assert summary["f1"] >= 0.90


def test_strong_gate_still_rejects_similar_title_with_different_food():
    potato = {
        "title": "Air Fryer Fries",
        "ingredients": ["russet potatoes", "olive oil", "salt"],
        "instructions": ["Cut potatoes into fries and air fry until crisp."],
    }
    zucchini = {
        "title": "Air Fryer Fries",
        "ingredients": ["zucchini", "breadcrumbs", "parmesan", "egg"],
        "instructions": ["Bread zucchini sticks and air fry until crisp."],
    }
    assert duplicate_similarity(potato, zucchini) < DEDUPE_THRESHOLD
