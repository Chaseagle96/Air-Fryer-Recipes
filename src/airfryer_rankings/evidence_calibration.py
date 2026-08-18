from __future__ import annotations

import json
import math
from collections import defaultdict
from dataclasses import replace
from pathlib import Path

from .models import RecipeRow, SourceConfig

DEFAULT_ASSIGNED_CONFIDENCE = {
    "verified": 1.00,
    "schema_only": 0.65,
    "visible_only": 0.65,
    "legacy_unverified": 0.60,
    "conflict": 0.25,
}


def _wilson_interval(successes: int, total: int, z: float = 1.96) -> tuple[float | None, float | None]:
    if total <= 0:
        return None, None
    proportion = successes / total
    denominator = 1.0 + z * z / total
    center = (proportion + z * z / (2 * total)) / denominator
    margin = z * math.sqrt((proportion * (1 - proportion) + z * z / (4 * total)) / total) / denominator
    return max(0.0, center - margin), min(1.0, center + margin)


def evaluate_evidence_labels(
    path: str | Path,
    fixture_root: str | Path = "tests/fixtures/real_pages",
    minimum_samples_per_status: int = 30,
) -> tuple[dict[str, dict], list[dict]]:
    label_path = Path(path)
    if not label_path.exists():
        return {}, []
    payload = json.loads(label_path.read_text(encoding="utf-8"))
    labels = payload.get("labels", payload if isinstance(payload, list) else [])
    outcomes: list[dict] = []
    grouped: dict[str, list[bool]] = defaultdict(list)
    from .extract import extract_recipe_from_html

    for index, label in enumerate(labels, 1):
        fixture = Path(fixture_root) / str(label.get("fixture", ""))
        if not fixture.exists():
            outcomes.append({"label_id": label.get("id", index), "status": "missing_fixture", "fixture": str(fixture)})
            continue
        html = fixture.read_text(encoding="utf-8")
        domain = str(label.get("source") or "fixture.invalid")
        url = str(label.get("url") or f"https://{domain}/fixture")
        row, _ = extract_recipe_from_html(html, url, domain, SourceConfig(domain))
        expected_status = str(label.get("expected_status") or "")
        expected_rating = label.get("expected_rating")
        expected_count = label.get("expected_rating_count")
        correct = row is not None
        if row is not None and expected_status:
            correct = correct and row.evidence_status == expected_status
        if row is not None and expected_rating is not None:
            correct = correct and abs(row.normalized_rating - float(expected_rating)) <= 0.011
        if row is not None and expected_count is not None:
            correct = correct and row.rating_count == int(expected_count)
        status = row.evidence_status if row is not None else expected_status or "missing"
        grouped[status].append(bool(correct))
        outcomes.append(
            {
                "label_id": label.get("id", index),
                "source": domain,
                "fixture": str(fixture),
                "expected_status": expected_status,
                "observed_status": row.evidence_status if row else None,
                "expected_rating": expected_rating,
                "observed_rating": row.normalized_rating if row else None,
                "expected_rating_count": expected_count,
                "observed_rating_count": row.rating_count if row else None,
                "correct": bool(correct),
            }
        )

    calibration: dict[str, dict] = {}
    statuses = set(DEFAULT_ASSIGNED_CONFIDENCE) | set(grouped)
    for status in sorted(statuses):
        values = grouped.get(status, [])
        successes = sum(values)
        total = len(values)
        lower, upper = _wilson_interval(successes, total)
        empirical = successes / total if total else None
        calibration[status] = {
            "evidence_status": status,
            "sample_count": total,
            "correct_count": successes,
            "empirical_accuracy": empirical,
            "wilson_95_low": lower,
            "wilson_95_high": upper,
            "assigned_confidence": DEFAULT_ASSIGNED_CONFIDENCE.get(status, 0.60),
            "calibration_error": (
                abs(empirical - DEFAULT_ASSIGNED_CONFIDENCE.get(status, 0.60)) if empirical is not None else None
            ),
            "ready": total >= minimum_samples_per_status,
            "minimum_samples": minimum_samples_per_status,
        }
    return calibration, outcomes


def apply_evidence_calibration(rows: list[RecipeRow], calibration: dict[str, dict]) -> list[RecipeRow]:
    output: list[RecipeRow] = []
    for row in rows:
        record = calibration.get(row.evidence_status) or {}
        if not record.get("ready") or record.get("empirical_accuracy") is None:
            output.append(row)
            continue
        empirical = max(0.0, min(1.0, float(record["empirical_accuracy"])))
        if row.evidence_status == "conflict":
            empirical = min(empirical, row.evidence_confidence)
        output.append(replace(row, evidence_confidence=empirical))
    return output
