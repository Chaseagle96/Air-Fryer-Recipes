from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from .models import RecipeRow, parse_dt
def detect_anomalies(state: dict, rows: Iterable[RecipeRow], coverage: Iterable[dict], events: Iterable[dict], run_at: str) -> list[dict]:
    anomalies: list[dict] = []
    for row in rows:
        stored = state.get("recipes", {}).get(row.recipe_id, {})
        prev_rating = stored.get("previous_rating")
        prev_count = stored.get("previous_rating_count")
        if prev_count is not None:
            delta = int(row.rating_count) - int(prev_count)
            if delta < 0:
                anomalies.append({"timestamp": run_at, "severity": "high", "type": "review_count_decrease", "recipe_id": row.recipe_id, "title": row.title, "source": row.source, "url": row.canonical_url or row.url, "detail": f"{prev_count} -> {row.rating_count}"})
            elif int(prev_count) > 0 and delta > max(250, int(prev_count) * 0.50):
                previous_seen = parse_dt(stored.get("previous_seen_at"))
                current_seen = parse_dt(run_at)
                hours = (current_seen - previous_seen).total_seconds() / 3600 if previous_seen and current_seen else None
                anomaly_type = "hourly_review_count_spike" if hours is not None and hours <= 2.0 else "review_count_spike"
                anomalies.append({"timestamp": run_at, "severity": "medium", "type": anomaly_type, "recipe_id": row.recipe_id, "title": row.title, "source": row.source, "url": row.canonical_url or row.url, "detail": f"+{delta} reviews" + (f" in {hours:.1f}h" if hours is not None else "")})
        if prev_rating is not None and abs(row.normalized_rating - float(prev_rating)) >= 0.25:
            anomalies.append({"timestamp": run_at, "severity": "medium", "type": "rating_shift", "recipe_id": row.recipe_id, "title": row.title, "source": row.source, "url": row.canonical_url or row.url, "detail": f"{float(prev_rating):.2f} -> {row.normalized_rating:.2f}"})
        if row.evidence_status == "conflict" or row.evidence_confidence < 0.60:
            anomalies.append({"timestamp": run_at, "severity": "high", "type": "evidence_conflict", "recipe_id": row.recipe_id, "title": row.title, "source": row.source, "url": row.canonical_url or row.url, "detail": f"confidence={row.evidence_confidence:.2f}"})

    canonical_map: dict[str, list[dict]] = defaultdict(list)
    for recipe in state.get("recipes", {}).values():
        canonical = recipe.get("canonical_url") or recipe.get("url")
        if canonical:
            canonical_map[canonical].append(recipe)
    for canonical, group in canonical_map.items():
        ids = {x.get("recipe_id") for x in group}
        if len(ids) > 1:
            anomalies.append({"timestamp": run_at, "severity": "medium", "type": "canonical_collision", "recipe_id": "", "title": "", "source": " | ".join(sorted({x.get("source", "") for x in group})), "url": canonical, "detail": f"{len(ids)} recipe IDs share canonical URL"})

    for item in coverage:
        if item.get("status") not in ("ok", None, "not_checked_this_run"):
            anomalies.append({"timestamp": run_at, "severity": "high", "type": "source_failure", "recipe_id": "", "title": "", "source": item.get("source", ""), "url": "", "detail": str(item.get("status"))})
    for event in events:
        if event.get("type") in {"recipe_disappeared", "malformed_rating_scale", "rating_evidence_conflict", "fetch_error"}:
            severity = "high" if event.get("type") in {"recipe_disappeared", "rating_evidence_conflict"} else "medium"
            anomalies.append({"timestamp": run_at, "severity": severity, "type": event.get("type"), "recipe_id": "", "title": "", "source": event.get("source", ""), "url": event.get("url", ""), "detail": str(event.get("status") or event.get("error") or "")})

    history = state.setdefault("anomaly_history", [])
    history.extend(anomalies)
    if len(history) > 2000:
        del history[:-2000]
    return anomalies


def source_reliability(state: dict, coverage: Iterable[dict], method: dict) -> list[dict]:
    current_coverage = {x.get("source", ""): x for x in coverage}
    history = state.get("source_history", [])[-30:]
    sources = set(current_coverage)
    for run in history:
        sources.update(x.get("source", "") for x in run.get("coverage", []))
    sources.update(x.get("source", "") for x in state.get("recipes", {}).values())
    adjustments = method.get("source_adjustments", {})
    anomaly_history = state.get("anomaly_history", [])[-1000:]
    result = []
    for source in sorted(x for x in sources if x):
        run_rows = [x for run in history for x in run.get("coverage", []) if x.get("source") == source and x.get("status") != "not_checked_this_run"]
        successful = sum(1 for x in run_rows if x.get("status") == "ok")
        recipe_rows = [x for x in state.get("recipes", {}).values() if x.get("source") == source]
        confidences = [float(x.get("evidence_confidence", 0.0)) for x in recipe_rows]
        anomalies = sum(1 for x in anomaly_history if x.get("source") == source)
        current = current_coverage.get(source, {})
        adj = adjustments.get(source, {})
        result.append(
            {
                "source": source,
                "runs_sampled": len(run_rows),
                "run_success_rate": successful / len(run_rows) if run_rows else None,
                "known_recipes": len(recipe_rows),
                "mean_evidence_confidence": sum(confidences) / len(confidences) if confidences else None,
                "anomalies_recent": anomalies,
                "source_rating_mean": adj.get("raw_mean"),
                "source_bias": adj.get("bias"),
                "current_targets": current.get("targets"),
                "current_verified": current.get("verified_recipes"),
                "current_status": current.get("status", "not_checked"),
            }
        )
    return result
