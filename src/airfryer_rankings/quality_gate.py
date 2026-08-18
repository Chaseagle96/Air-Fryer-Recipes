from __future__ import annotations

import csv
import json
from pathlib import Path


class PublishGateError(RuntimeError):
    pass


def load_previous_serving_snapshot(output_dir: str | Path = "output") -> tuple[dict, list[dict]]:
    root = Path(output_dir)
    summary: dict = {}
    rankings: list[dict] = []
    summary_path = root / "summary.json"
    leaderboard_path = root / "leaderboard.csv"
    if summary_path.exists():
        try:
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
        except Exception:
            summary = {}
    if leaderboard_path.exists():
        try:
            with leaderboard_path.open(newline="", encoding="utf-8") as handle:
                rankings = list(csv.DictReader(handle))
        except Exception:
            rankings = []
    return summary, rankings


def evaluate_publish_gate(
    previous_summary: dict,
    previous_rankings: list[dict],
    ranked: list[dict],
    metrics: dict,
    *,
    mode: str,
    model_version: int,
    deduplicated_count: int,
) -> dict:
    failures: list[str] = []
    warnings: list[str] = []
    details: dict = {}
    previous_count = int(previous_summary.get("ranked_recipes") or 0)
    current_count = len(ranked)
    details["previous_ranked_recipes"] = previous_count
    details["current_ranked_recipes"] = current_count
    if current_count == 0:
        failures.append("leaderboard is empty")
    elif previous_count >= 100:
        ratio = current_count / previous_count
        details["ranked_recipe_retention"] = ratio
        if ratio < 0.80:
            failures.append(f"ranked recipe count retained only {ratio:.1%} of previous production output")
    if previous_count >= 50 and current_count < 50:
        failures.append("Top 50 cannot be produced from current ranking")

    conflict_rate = metrics.get("evidence_conflict_rate")
    if conflict_rate is not None and float(conflict_rate) > 0.20:
        failures.append(f"evidence conflict rate is catastrophically high at {float(conflict_rate):.1%}")
    elif conflict_rate is not None and float(conflict_rate) > 0.10:
        warnings.append(f"evidence conflict rate elevated at {float(conflict_rate):.1%}")

    previous_model = int(previous_summary.get("model_version") or model_version)
    previous_top50 = [str(row.get("recipe_id") or "") for row in previous_rankings[:50] if row.get("recipe_id")]
    current_top50 = [str(row.get("recipe_id") or "") for row in ranked[:50]]
    if previous_top50 and current_top50:
        overlap = len(set(previous_top50) & set(current_top50)) / min(len(previous_top50), len(current_top50))
        details["top50_overlap_previous"] = overlap
        if previous_model == model_version and overlap < 0.35:
            failures.append(f"Top-50 overlap collapsed to {overlap:.1%} without a model-version change")
        elif previous_model != model_version and overlap < 0.35:
            warnings.append(f"model version changed and Top-50 overlap is only {overlap:.1%}")

    previous_deduplicated = int(previous_summary.get("deduplicated_count") or 0)
    details["previous_deduplicated_count"] = previous_deduplicated
    details["current_deduplicated_count"] = int(deduplicated_count)
    spike_threshold = max(20, previous_deduplicated * 10 + 5)
    if int(deduplicated_count) > spike_threshold:
        failures.append(
            f"deduplication count spiked to {deduplicated_count} from {previous_deduplicated}; threshold is {spike_threshold}"
        )

    if int(metrics.get("legacy_evidence_pending") or 0) > 0 and mode not in {"backfill", "smoke"}:
        warnings.append("legacy evidence remains pending outside explicit backfill mode")
    if int(metrics.get("http_429") or 0) > 10:
        warnings.append("publisher throttling is elevated; crawl cadence may need reduction")

    return {
        "passed": not failures,
        "mode": mode,
        "model_version": model_version,
        "failures": failures,
        "warnings": warnings,
        "metrics": details,
    }


def write_quality_gate(path: str | Path, result: dict) -> str:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return str(target)


def assert_publishable(result: dict) -> None:
    if result.get("passed"):
        return
    failures = "; ".join(str(value) for value in result.get("failures", [])) or "unknown publication gate failure"
    raise PublishGateError(failures)
