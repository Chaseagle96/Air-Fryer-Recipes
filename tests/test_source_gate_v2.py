from __future__ import annotations

from airfryer_rankings import source_expansion as legacy
from airfryer_rankings.source_expansion_v2 import (
    SOURCE_GATE_VERSION,
    SampledPage,
    hard_gate_failures,
    install_gate_v2,
    qualification_metrics,
    score_source_quality,
)


def _recipe_page(*, rating: bool, extracted: bool) -> SampledPage:
    return SampledPage(
        url="https://publisher.example/air-fryer-test",
        fetched=True,
        final_url="https://publisher.example/air-fryer-test",
        is_recipe=True,
        vertical_relevant=True,
        title="Air Fryer Test",
        ingredients=("one", "two", "three"),
        instructions=("step one", "step two"),
        author="Test Kitchen",
        field_completeness=1.0,
        ranking_extractable=extracted,
        has_rating=rating,
        evidence_status="verified" if rating else "missing",
        evidence_confidence=1.0 if rating else 0.0,
        recipe_payload={
            "title": "Air Fryer Test",
            "source": "publisher.example",
            "url": "https://publisher.example/air-fryer-test",
            "canonical_url": "https://publisher.example/air-fryer-test",
            "ingredients": ["one", "two", "three"],
            "instructions": ["step one", "step two"],
            "author": "Test Kitchen",
            "instruction_simhash": 0,
            "image_fingerprint": "",
            "image_perceptual_hash": "",
        },
    )


def _policy() -> dict:
    return {
        "target_vertical_recipe_count": 20,
        "weights": {
            "vertical_relevance": 0.20,
            "extraction_reliability": 0.20,
            "editorial_provenance": 0.15,
            "crawl_stability": 0.15,
            "rating_integrity": 0.10,
            "unique_contribution": 0.10,
            "freshness": 0.05,
            "general_quality": 0.05,
        },
        "hard_gates": {
            "min_pages_sampled": 1,
            "min_pages_fetched": 1,
            "min_vertical_recipe_count": 1,
            "min_fetch_success_rate": 0.70,
            "min_recipe_structure_rate": 0.55,
            "min_vertical_relevance_ratio": 0.40,
            "min_substantive_recipe_ratio": 0.55,
            "min_ranking_evidence_pages_for_extraction_gate": 3,
            "min_extraction_success_rate": 0.60,
            "max_external_canonical_ratio": 0.25,
            "max_within_source_duplicate_ratio": 0.65,
            "max_trap_url_ratio": 0.30,
            "max_rating_conflict_ratio": 0.50,
        },
    }


def test_gate_v2_is_installed_into_shared_engine() -> None:
    install_gate_v2()
    assert SOURCE_GATE_VERSION == 2
    assert legacy.SOURCE_GATE_VERSION == 2
    assert legacy.qualification_metrics is qualification_metrics


def test_extraction_reliability_is_conditional_on_ranking_evidence() -> None:
    pages = [
        _recipe_page(rating=True, extracted=True),
        _recipe_page(rating=False, extracted=False),
    ]
    metrics = qualification_metrics(
        pages,
        candidate_url_count=10,
        robots_status="ok",
        run_at="2026-08-19T00:00:00+00:00",
        existing_recipes=[],
    )

    assert metrics["recipes_recognized"] == 2
    assert metrics["recipes_extracted"] == 1
    assert metrics["ranking_evidence_pages"] == 1
    assert metrics["ranking_evidence_coverage_ratio"] == 0.5
    assert metrics["ranking_row_yield"] == 0.5
    assert metrics["extraction_success_rate"] == 1.0


def test_rating_free_recipe_source_is_not_mislabeled_extraction_failure() -> None:
    metrics = qualification_metrics(
        [_recipe_page(rating=False, extracted=False)],
        candidate_url_count=20,
        robots_status="ok",
        run_at="2026-08-19T00:00:00+00:00",
        existing_recipes=[],
    )
    assert metrics["ranking_evidence_pages"] == 0
    assert metrics["extraction_success_rate"] is None

    score, components = score_source_quality(metrics, _policy())
    permanent, temporary = hard_gate_failures(metrics, _policy())
    assert score > 0
    assert components["extraction_reliability"] > 0
    assert "ranking_extractor_incompatible" not in permanent
    assert not temporary


def test_repeated_ranking_evidence_extraction_failure_is_hard_gate() -> None:
    pages = [
        _recipe_page(rating=True, extracted=False),
        _recipe_page(rating=True, extracted=False),
        _recipe_page(rating=True, extracted=True),
        _recipe_page(rating=False, extracted=False),
    ]
    metrics = qualification_metrics(
        pages,
        candidate_url_count=20,
        robots_status="ok",
        run_at="2026-08-19T00:00:00+00:00",
        existing_recipes=[],
    )
    assert metrics["ranking_evidence_pages"] == 3
    assert metrics["extraction_success_rate"] == 1 / 3
    permanent, _ = hard_gate_failures(metrics, _policy())
    assert "ranking_extractor_incompatible" in permanent


def test_sparse_ranking_evidence_does_not_trigger_low_sample_hard_rejection() -> None:
    pages = [
        _recipe_page(rating=True, extracted=False),
        _recipe_page(rating=False, extracted=False),
        _recipe_page(rating=False, extracted=False),
    ]
    metrics = qualification_metrics(
        pages,
        candidate_url_count=20,
        robots_status="ok",
        run_at="2026-08-19T00:00:00+00:00",
        existing_recipes=[],
    )
    assert metrics["ranking_evidence_pages"] == 1
    assert metrics["extraction_success_rate"] == 0.0
    permanent, _ = hard_gate_failures(metrics, _policy())
    assert "ranking_extractor_incompatible" not in permanent
