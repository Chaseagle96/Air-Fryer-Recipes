from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pandas as pd


def _frame(rows) -> pd.DataFrame:
    if isinstance(rows, dict):
        rows = [rows]
    frame = pd.DataFrame(list(rows or []))
    if frame.empty:
        return frame
    for column in frame.columns:
        if frame[column].map(lambda x: isinstance(x, (dict, list, tuple, set))).any():
            frame[column] = frame[column].map(
                lambda x: json.dumps(x, sort_keys=True, default=str) if isinstance(x, (dict, list, tuple, set)) else x
            )
    return frame


def _replace_table(connection, name: str, rows) -> None:
    frame = _frame(rows)
    connection.execute(f'DROP TABLE IF EXISTS "{name}"')
    if frame.empty:
        connection.execute(f'CREATE TABLE "{name}" (empty INTEGER)')
        return
    relation = f"_{name}_frame"
    connection.register(relation, frame)
    connection.execute(f'CREATE TABLE "{name}" AS SELECT * FROM {relation}')
    connection.unregister(relation)


def write_duckdb_cache(
    path: str | Path,
    *,
    ranked: list[dict],
    observations: list[dict],
    ranking_records: list[dict],
    source_health: list[dict],
    source_reliability: list[dict],
    anomalies: list[dict],
    calibration: dict[str, dict],
    robustness: dict,
    dedupe_summary: dict,
    dedupe_results: list[dict],
) -> str:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = duckdb.connect(str(path))
    try:
        _replace_table(connection, "current_rankings", ranked)
        _replace_table(connection, "observations", observations)
        _replace_table(connection, "ranking_history", ranking_records)
        _replace_table(connection, "source_health", source_health)
        _replace_table(connection, "source_reliability", source_reliability)
        _replace_table(connection, "anomalies", anomalies)
        _replace_table(connection, "uncertainty_calibration", list(calibration.values()))
        _replace_table(connection, "dedupe_benchmark", dedupe_results)
        _replace_table(connection, "dedupe_benchmark_summary", dedupe_summary)
        robustness_summary = {k: v for k, v in robustness.items() if k != "simulations"}
        _replace_table(connection, "ranking_robustness_summary", robustness_summary)
        _replace_table(connection, "ranking_robustness_simulations", robustness.get("simulations", []))
        connection.execute("CREATE OR REPLACE VIEW top50 AS SELECT * FROM current_rankings WHERE rank <= 50 ORDER BY rank")
        connection.execute("CREATE OR REPLACE VIEW top10 AS SELECT * FROM current_rankings WHERE rank <= 10 ORDER BY rank")
        connection.execute("CHECKPOINT")
    finally:
        connection.close()
    return str(path)
