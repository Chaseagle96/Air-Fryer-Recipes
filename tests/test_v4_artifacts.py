from io import BytesIO

import duckdb
from PIL import Image

from airfryer_rankings.analytics import write_duckdb_cache
from airfryer_rankings.media import perceptual_hash_bytes


def _png_bytes(value: int) -> bytes:
    image = Image.new("L", (16, 16), color=value)
    out = BytesIO()
    image.save(out, format="PNG")
    return out.getvalue()


def test_perceptual_hash_is_content_based_and_deterministic():
    first = perceptual_hash_bytes(_png_bytes(120))
    second = perceptual_hash_bytes(_png_bytes(120))
    assert first == second
    assert len(first) == 16


def test_duckdb_cache_exposes_queryable_research_tables(tmp_path):
    path = tmp_path / "analytics.duckdb"
    write_duckdb_cache(
        path,
        ranked=[{"rank": 1, "recipe_id": "a", "title": "Air Fryer Chicken", "hierarchical_score": 4.7}],
        observations=[{"recipe_id": "a", "timestamp": "2026-08-18T20:00:00+00:00", "rating": 4.9, "rating_count": 100}],
        ranking_records=[{"recipe_id": "a", "timestamp": "2026-08-18T20:00:00+00:00", "rank": 1}],
        source_health=[{"source": "x.com", "healthy_at_last_check": True}],
        source_reliability=[{"source": "x.com", "run_success_rate": 1.0}],
        anomalies=[],
        calibration={"100-499": {"bucket": "100-499", "sample_pairs": 1, "ready": False}},
        robustness={"simulation_count": 36, "simulations": [{"top10_overlap": 1.0}]},
        dedupe_summary={"benchmark_pairs": 2, "precision": 1.0, "recall": 1.0, "f1": 1.0},
        dedupe_results=[{"pair_id": "x", "outcome": "TP"}],
    )
    connection = duckdb.connect(str(path), read_only=True)
    try:
        tables = {row[0] for row in connection.execute("SHOW TABLES").fetchall()}
        assert "current_rankings" in tables
        assert "observations" in tables
        assert "source_health" in tables
        assert "ranking_robustness_simulations" in tables
        assert connection.execute("SELECT COUNT(*) FROM top10").fetchone()[0] == 1
    finally:
        connection.close()
