from __future__ import annotations

from airfryer_rankings.source_hygiene import retire_nonpublisher_candidates
from airfryer_rankings.source_registry import ACTIVE, CANDIDATE, REJECTED, empty_source_registry, record_candidate_discovery
from airfryer_rankings.source_security import is_non_publisher_domain


def _candidate(registry: dict, domain: str) -> dict:
    record, _ = record_candidate_discovery(
        registry,
        domain=domain,
        provider="unit",
        query="air fryer recipes",
        discovery_url=f"https://{domain}/air-fryer-recipes",
        timestamp="2026-08-19T00:00:00+00:00",
    )
    assert record is not None
    return record


def test_obvious_retail_affiliate_aggregator_and_auth_hosts_are_not_publishers() -> None:
    for domain in (
        "amzn.to",
        "amzlink.to",
        "geni.us",
        "rstyle.me",
        "walmart.com",
        "wayfair.com",
        "barnesandnoble.com",
        "yummly.com",
        "share.flipboard.com",
        "auth.tasteofhome.com",
    ):
        assert is_non_publisher_domain(domain), domain

    assert not is_non_publisher_domain("tasteofhome.com")
    assert not is_non_publisher_domain("forktospoon.com")


def test_candidate_hygiene_rejects_nonpublishers_without_erasing_history() -> None:
    registry = empty_source_registry("air_fryer")
    retail = _candidate(registry, "wayfair.com")
    publisher = _candidate(registry, "publisher.example")
    before_evidence = list(retail["discovery_evidence"])

    retired = retire_nonpublisher_candidates(
        registry,
        blocked_suffixes=(),
        timestamp="2026-08-19T01:00:00+00:00",
    )

    assert retired == 1
    assert retail["status"] == REJECTED
    assert retail["rediscovery_blocked"] is True
    assert retail["discovery_evidence"] == before_evidence
    assert publisher["status"] == CANDIDATE
    assert any(
        event["event"] == "SOURCE_REJECTED"
        and event["domain"] == "wayfair.com"
        and event["metrics"] == {"classification": "non_publisher_domain"}
        for event in registry["audit"]
    )


def test_candidate_hygiene_respects_explicit_maintainer_approval() -> None:
    registry = empty_source_registry("air_fryer")
    record = _candidate(registry, "wayfair.com")
    registry["manual_overrides"]["wayfair.com"] = {
        "decision": "approve",
        "reason": "explicit test override",
    }
    record["status"] = ACTIVE

    retired = retire_nonpublisher_candidates(
        registry,
        blocked_suffixes=(),
        timestamp="2026-08-19T01:00:00+00:00",
    )

    assert retired == 0
    assert record["status"] == ACTIVE
