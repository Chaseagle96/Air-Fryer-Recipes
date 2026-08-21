from __future__ import annotations

import requests

import airfryer_rankings.http as http_client
from airfryer_rankings.models import UA, SourceConfig


class FakeResponse:
    def __init__(self, *, status_code: int = 200, text: str = "") -> None:
        self.status_code = status_code
        self.text = text


def _http_error(status_code: int) -> requests.HTTPError:
    response = requests.Response()
    response.status_code = status_code
    return requests.HTTPError(response=response)


def test_successful_robots_rules_and_sitemaps_are_followed(monkeypatch) -> None:
    robots = "User-agent: *\nDisallow: /private/\nSitemap: https://example.com/recipes.xml\n"
    monkeypatch.setattr(
        http_client,
        "get_for_source",
        lambda session, url, cfg, timeout=20, headers=None: FakeResponse(text=robots),
    )

    parser, sitemaps, robots_text, status = http_client.robots_and_sitemaps(object(), SourceConfig("example.com"))

    assert status == "ok"
    assert robots_text == robots
    assert sitemaps == ["https://example.com/recipes.xml"]
    assert parser.can_fetch(UA, "https://example.com/public/recipe")
    assert not parser.can_fetch(UA, "https://example.com/private/recipe")


def test_4xx_robots_unavailable_preserves_unrestricted_policy(monkeypatch) -> None:
    def unavailable(*args, **kwargs):
        raise _http_error(404)

    monkeypatch.setattr(http_client, "get_for_source", unavailable)

    parser, sitemaps, robots_text, status = http_client.robots_and_sitemaps(object(), SourceConfig("example.com"))

    assert status == "ok"
    assert robots_text == ""
    assert sitemaps == ["https://example.com/sitemap.xml"]
    assert parser.can_fetch(UA, "https://example.com/recipe")


def test_5xx_robots_unreachable_fails_closed_and_suppresses_sitemaps(monkeypatch) -> None:
    def unreachable(*args, **kwargs):
        raise _http_error(503)

    monkeypatch.setattr(http_client, "get_for_source", unreachable)

    parser, sitemaps, robots_text, status = http_client.robots_and_sitemaps(object(), SourceConfig("example.com"))

    assert status == "unreachable:http_503"
    assert robots_text == ""
    assert sitemaps == []
    assert not parser.can_fetch(UA, "https://example.com/recipe")


def test_network_failure_fails_closed_and_suppresses_sitemaps(monkeypatch) -> None:
    def timeout(*args, **kwargs):
        raise requests.Timeout("simulated timeout")

    monkeypatch.setattr(http_client, "get_for_source", timeout)

    parser, sitemaps, robots_text, status = http_client.robots_and_sitemaps(object(), SourceConfig("example.com"))

    assert status == "unreachable:Timeout"
    assert robots_text == ""
    assert sitemaps == []
    assert not parser.can_fetch(UA, "https://example.com/recipe")


def test_non_http_retrieval_failure_fails_closed(monkeypatch) -> None:
    def unsafe_target(*args, **kwargs):
        raise ValueError("simulated safety failure")

    monkeypatch.setattr(http_client, "get_for_source", unsafe_target)

    parser, sitemaps, _, status = http_client.robots_and_sitemaps(
        object(),
        SourceConfig("example.com", origin="discovered"),
    )

    assert status == "unreachable:ValueError"
    assert sitemaps == []
    assert not parser.can_fetch(UA, "https://example.com/recipe")


def test_configured_sitemap_is_retained_when_robots_is_unavailable(monkeypatch) -> None:
    def unavailable(*args, **kwargs):
        raise _http_error(410)

    monkeypatch.setattr(http_client, "get_for_source", unavailable)
    cfg = SourceConfig("example.com", sitemap_urls=("https://example.com/custom-sitemap.xml",))

    parser, sitemaps, _, status = http_client.robots_and_sitemaps(object(), cfg)

    assert status == "ok"
    assert sitemaps == ["https://example.com/custom-sitemap.xml"]
    assert parser.can_fetch(UA, "https://example.com/recipe")
