from __future__ import annotations

from collections.abc import Iterable

from .source_registry import BLOCKED, REJECTED, transition_source
from .source_security import is_non_publisher_domain


def retire_nonpublisher_candidates(
    registry: dict,
    *,
    blocked_suffixes: Iterable[str] = (),
    timestamp: str,
) -> int:
    """Audit-retire discovered candidates that are not recipe publishers.

    Existing discovery history is preserved. Automatic cleanup only applies to
    machine-managed candidates; pinned or explicitly approved/restored sources retain
    maintainer authority and are left untouched.
    """

    retired = 0
    overrides = registry.get("manual_overrides", {}) or {}
    candidates = registry.get("candidates", {}) or {}
    for domain, record in candidates.items():
        override = overrides.get(domain, {}) if isinstance(overrides, dict) else {}
        maintainer_protected = bool(
            record.get("pinned")
            or override.get("pinned")
            or str(override.get("decision") or "") in {"approve", "restore"}
        )
        if maintainer_protected or not is_non_publisher_domain(domain, blocked_suffixes):
            continue
        if str(record.get("status") or "") == BLOCKED:
            record["rediscovery_blocked"] = True
            continue
        reason = "automatic non-publisher rejection: retail, affiliate, aggregator, auth, or infrastructure domain"
        if (
            str(record.get("status") or "") == REJECTED
            and bool(record.get("rediscovery_blocked"))
            and str(record.get("rejection_reason") or "") == reason
        ):
            continue
        record["rediscovery_blocked"] = True
        transition_source(
            registry,
            domain,
            REJECTED,
            reason,
            timestamp=timestamp,
            metrics={"classification": "non_publisher_domain"},
            thresholds={},
            event="SOURCE_REJECTED",
        )
        retired += 1
    return retired
