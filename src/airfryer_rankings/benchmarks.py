from __future__ import annotations

import json
from pathlib import Path

from .dedupe import duplicate_similarity
from .models import instruction_simhash


def _prepare(recipe: dict) -> dict:
    item = dict(recipe)
    instructions = item.get("instructions") or []
    if instructions and not item.get("instruction_simhash"):
        item["instruction_simhash"] = instruction_simhash(instructions)
    return item


def evaluate_dedupe_benchmark(path: str | Path, threshold: float = 0.88) -> tuple[dict, list[dict]]:
    p = Path(path)
    if not p.exists():
        return {"benchmark_pairs": 0, "precision": None, "recall": None, "f1": None, "threshold": threshold}, []
    payload = json.loads(p.read_text())
    pairs = payload.get("pairs", payload if isinstance(payload, list) else [])
    tp = fp = tn = fn = 0
    results = []
    for index, pair in enumerate(pairs, 1):
        left = _prepare(pair.get("left", {}))
        right = _prepare(pair.get("right", {}))
        expected = bool(pair.get("duplicate"))
        score = duplicate_similarity(left, right)
        predicted = score >= threshold
        if expected and predicted:
            tp += 1
            outcome = "TP"
        elif expected and not predicted:
            fn += 1
            outcome = "FN"
        elif not expected and predicted:
            fp += 1
            outcome = "FP"
        else:
            tn += 1
            outcome = "TN"
        results.append(
            {
                "pair_id": pair.get("id", index),
                "expected_duplicate": expected,
                "predicted_duplicate": predicted,
                "similarity": score,
                "outcome": outcome,
                "left_title": left.get("title", ""),
                "right_title": right.get("title", ""),
                "note": pair.get("note", ""),
            }
        )
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    f1 = 2 * precision * recall / (precision + recall) if precision is not None and recall is not None and precision + recall else None
    summary = {
        "benchmark_version": payload.get("version", 1) if isinstance(payload, dict) else 1,
        "benchmark_pairs": len(results),
        "true_positives": tp,
        "false_positives": fp,
        "true_negatives": tn,
        "false_negatives": fn,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "threshold": threshold,
    }
    return summary, results
