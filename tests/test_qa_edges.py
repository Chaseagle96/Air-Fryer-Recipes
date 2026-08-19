from airfryer_rankings.models import RecipeRow, SourceConfig
from airfryer_rankings.observability import build_pipeline_metrics
from airfryer_rankings.qa import detect_anomalies, source_health_summary, source_reliability


def test_source_health_and_reliability_distinguish_stale_unchecked_and_degraded_sources():
    state = {
        "recipes": {
            "a": {
                "recipe_id": "a",
                "source": "good.com",
                "evidence_confidence": 1.0,
                "needs_evidence_backfill": False,
            },
            "b": {
                "recipe_id": "b",
                "source": "bad.com",
                "evidence_confidence": 0.60,
                "needs_evidence_backfill": True,
            },
        },
        "source_history": [
            {
                "run_at": "2026-08-18T18:00:00+00:00",
                "coverage": [
                    {"source": "good.com", "status": "ok", "targets": 2, "verified_recipes": 2},
                    {"source": "bad.com", "status": "degraded", "targets": 1, "verified_recipes": 0},
                    {"source": "idle.com", "status": "not_checked_this_run"},
                ],
            },
            {
                "run_at": "2026-08-18T20:00:00+00:00",
                "coverage": [
                    {"source": "good.com", "status": "ok", "targets": 1, "verified_recipes": 1},
                    {"source": "bad.com", "status": "not_checked_this_run"},
                ],
            },
        ],
        "anomaly_history": [
            {"source": "bad.com", "type": "source_failure"},
            {"source": "bad.com", "type": "fetch_error"},
        ],
        "migration": {"legacy_evidence_pending": 1},
    }
    coverage = [
        {"source": "good.com", "status": "ok", "targets": 1, "verified_recipes": 1, "elapsed_seconds": 0.2},
        {"source": "bad.com", "status": "degraded", "targets": 1, "verified_recipes": 0, "elapsed_seconds": 0.4},
        {"source": "idle.com", "status": "not_checked_this_run"},
    ]
    configs = [SourceConfig("good.com"), SourceConfig("bad.com"), SourceConfig("idle.com")]

    health, summary = source_health_summary(state, coverage, configs, "2026-08-18T21:00:00+00:00")
    by_source = {row["source"]: row for row in health}
    assert by_source["good.com"]["successful_this_run"] is True
    assert by_source["bad.com"]["degraded_this_run"] is True
    assert by_source["idle.com"]["checked_this_run"] is False
    assert summary["sources_checked_this_run"] == 2
    assert summary["sources_degraded_this_run"] == 1

    metrics, _, _ = build_pipeline_metrics(
        state,
        coverage,
        [],
        [{"recipe_id": "a"}],
        [],
        health,
        [],
        [{"url": "https://good.com/a"}, {"url": "https://bad.com/b"}],
        "2026-08-18T21:00:00+00:00",
    )
    assert metrics["sources_stale_24h"] == 1
    assert metrics["sources_stale_7d"] == 1
    assert metrics["legacy_evidence_pending"] == 1

    method = {
        "source_adjustments": {
            "good.com": {"raw_mean": 4.8, "bias": 0.02},
            "bad.com": {"raw_mean": 4.4, "bias": -0.05},
        }
    }
    reliability = source_reliability(state, coverage, method)
    rel = {row["source"]: row for row in reliability}
    assert rel["good.com"]["run_success_rate"] == 1.0
    assert rel["good.com"]["mean_evidence_confidence"] == 1.0
    assert rel["bad.com"]["legacy_evidence_pending"] == 1
    assert rel["bad.com"]["anomalies_recent"] == 2
    assert rel["bad.com"]["current_status"] == "degraded"


def test_anomaly_detector_covers_conflict_spike_disappearance_fetch_and_source_failure():
    state = {
        "recipes": {
            "r": {
                "recipe_id": "r",
                "previous_rating": 4.9,
                "previous_rating_count": 100,
                "previous_seen_at": "2026-08-18T20:00:00+00:00",
                "canonical_url": "https://example.com/r",
                "url": "https://example.com/r",
                "source": "example.com",
            },
            "collision": {
                "recipe_id": "collision",
                "canonical_url": "https://example.com/r",
                "url": "https://example.com/other",
                "source": "other.com",
            },
        },
        "anomaly_history": [],
    }
    row = RecipeRow(
        recipe_id="r",
        title="Air Fryer Test",
        source="example.com",
        url="https://example.com/r",
        rating=4.5,
        rating_count=400,
        best_rating=5.0,
        normalized_rating=4.5,
        retrieved_at="2026-08-18T21:00:00+00:00",
        canonical_url="https://example.com/r",
        evidence_confidence=0.25,
        evidence_status="conflict",
    )
    anomalies = detect_anomalies(
        state,
        [row],
        [{"source": "example.com", "status": "degraded"}],
        [
            {"type": "recipe_disappeared", "source": "example.com", "url": row.url, "status": 404},
            {"type": "fetch_error", "source": "example.com", "url": row.url, "status": 500},
            {"type": "malformed_rating_scale", "source": "example.com", "url": row.url},
        ],
        "2026-08-18T21:00:00+00:00",
    )
    kinds = {item["type"] for item in anomalies}
    assert "hourly_review_count_spike" in kinds
    assert "rating_shift" in kinds
    assert "evidence_conflict" in kinds
    assert "canonical_collision" in kinds
    assert "source_failure" in kinds
    assert "recipe_disappeared" in kinds
    assert "fetch_error" in kinds
    assert "malformed_rating_scale" in kinds
