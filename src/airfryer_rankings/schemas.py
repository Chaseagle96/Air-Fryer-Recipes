from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any, NotRequired, TypedDict

EVIDENCE_STATUSES = {"verified", "schema_only", "visible_only", "conflict", "legacy_unverified"}


class ObservationRecord(TypedDict):
    recipe_id: str
    timestamp: str
    source: str
    url: str
    title: str
    rating: float
    rating_count: int
    evidence_confidence: float
    evidence_status: str
    extraction_method: str
    page_hash: str
    schema_version: int
    dom_fingerprint: NotRequired[str]
    schema_signature: NotRequired[str]


class RankedRecipeRecord(TypedDict):
    recipe_id: str
    title: str
    source: str
    url: str
    rating: float
    rating_count: int
    hierarchical_score: float
    rank: int
    evidence_confidence: float
    evidence_status: str
    evidence_grade: NotRequired[str]
    rank_confidence: NotRequired[float]
    rank_range_low: NotRequired[int]
    rank_range_high: NotRequired[int]


class SourceHealthRecord(TypedDict):
    source: str
    checked_this_run: bool
    successful_this_run: bool
    degraded_this_run: bool
    last_checked_at: NotRequired[str | None]
    hours_since_last_check: NotRequired[float | None]


class QualityGateRecord(TypedDict):
    passed: bool
    failures: list[str]
    warnings: list[str]
    metrics: dict[str, Any]


def _require(row: Mapping[str, Any], keys: Iterable[str], kind: str) -> None:
    missing = [key for key in keys if key not in row]
    if missing:
        raise ValueError(f"{kind} missing required fields: {', '.join(missing)}")


def _number(value: Any, field: str, kind: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{kind}.{field} must be numeric, got {type(value).__name__}")
    return float(value)


def validate_observation_record(row: Mapping[str, Any]) -> None:
    _require(
        row,
        (
            "recipe_id",
            "timestamp",
            "source",
            "url",
            "title",
            "rating",
            "rating_count",
            "evidence_confidence",
            "evidence_status",
            "extraction_method",
            "page_hash",
            "schema_version",
        ),
        "observation",
    )
    rating = _number(row["rating"], "rating", "observation")
    confidence = _number(row["evidence_confidence"], "evidence_confidence", "observation")
    if not 0.0 <= rating <= 5.05:
        raise ValueError(f"observation.rating outside normalized five-star range: {rating}")
    if not 0.0 <= confidence <= 1.0:
        raise ValueError(f"observation.evidence_confidence outside [0, 1]: {confidence}")
    count = row["rating_count"]
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        raise ValueError("observation.rating_count must be a non-negative integer")
    if str(row["evidence_status"]) not in EVIDENCE_STATUSES:
        raise ValueError(f"observation.evidence_status is unknown: {row['evidence_status']}")


def validate_ranked_recipe(row: Mapping[str, Any]) -> None:
    _require(
        row,
        (
            "recipe_id",
            "title",
            "source",
            "url",
            "rating",
            "rating_count",
            "hierarchical_score",
            "rank",
            "evidence_confidence",
            "evidence_status",
        ),
        "ranking",
    )
    score = _number(row["hierarchical_score"], "hierarchical_score", "ranking")
    confidence = _number(row["evidence_confidence"], "evidence_confidence", "ranking")
    if not 0.0 <= score <= 5.05:
        raise ValueError(f"ranking.hierarchical_score outside expected range: {score}")
    if not 0.0 <= confidence <= 1.0:
        raise ValueError(f"ranking.evidence_confidence outside [0, 1]: {confidence}")
    rank = row["rank"]
    if isinstance(rank, bool) or not isinstance(rank, int) or rank <= 0:
        raise ValueError("ranking.rank must be a positive integer")
    rank_confidence = row.get("rank_confidence")
    if rank_confidence is not None and not 0.0 <= _number(rank_confidence, "rank_confidence", "ranking") <= 1.0:
        raise ValueError("ranking.rank_confidence outside [0, 1]")


def validate_source_health(row: Mapping[str, Any]) -> None:
    _require(row, ("source", "checked_this_run", "successful_this_run", "degraded_this_run"), "source_health")
    for field in ("checked_this_run", "successful_this_run", "degraded_this_run"):
        if not isinstance(row[field], bool):
            raise ValueError(f"source_health.{field} must be boolean")


def validate_records(rows: Iterable[Mapping[str, Any]], validator) -> None:
    for index, row in enumerate(rows):
        try:
            validator(row)
        except ValueError as exc:
            raise ValueError(f"record {index}: {exc}") from exc
