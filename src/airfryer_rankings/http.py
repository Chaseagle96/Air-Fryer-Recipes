from __future__ import annotations

import gzip
from typing import Iterator
from urllib.robotparser import RobotFileParser
from xml.etree import ElementTree as ET

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .models import HEADERS, UA, SourceConfig

def make_session() -> requests.Session:
    session = requests.Session()
    retries = Retry(
        total=3,
        connect=3,
        read=3,
        status=3,
        backoff_factor=0.6,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET", "HEAD"}),
        respect_retry_after_header=True,
    )
    adapter = HTTPAdapter(max_retries=retries, pool_connections=20, pool_maxsize=20)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def get(session: requests.Session, url: str, timeout: int = 20, headers: dict | None = None) -> requests.Response:
    merged = dict(HEADERS)
    if headers:
        merged.update(headers)
    response = session.get(url, headers=merged, timeout=timeout)
    if response.status_code != 304:
        response.raise_for_status()
    return response


def robots_and_sitemaps(session: requests.Session, cfg: SourceConfig) -> tuple[RobotFileParser, list[str], str, str]:
    robots_url = f"https://{cfg.domain}/robots.txt"
    robots_text = ""
    robots_status = "ok"
    try:
        robots_text = get(session, robots_url, 15).text
    except Exception as exc:
        robots_status = f"unavailable:{type(exc).__name__}"

    parser = RobotFileParser()
    parser.set_url(robots_url)
    try:
        if robots_text:
            parser.parse(robots_text.splitlines())
        else:
            parser.parse(["User-agent: *", "Allow: /"])
    except Exception:
        parser = RobotFileParser()
        parser.set_url(robots_url)
        parser.parse(["User-agent: *", "Allow: /"])
        robots_status = "parse_fallback_allow"

    sitemaps = list(cfg.sitemap_urls)
    for line in robots_text.splitlines():
        if line.lower().startswith("sitemap:"):
            value = line.split(":", 1)[1].strip()
            if value:
                sitemaps.append(value)
    if not sitemaps:
        sitemaps = [f"https://{cfg.domain}/sitemap.xml"]
    return parser, list(dict.fromkeys(sitemaps)), robots_text, robots_status


def _xml_bytes(response: requests.Response, url: str) -> bytes:
    content = response.content
    if url.lower().endswith(".gz") or content[:2] == b"\x1f\x8b":
        try:
            return gzip.decompress(content)
        except OSError:
            return content
    return content


def iter_sitemap_records(
    session: requests.Session,
    sitemap_url: str,
    seen: set[str] | None = None,
    max_docs: int = 150,
) -> Iterator[dict]:
    seen = seen if seen is not None else set()
    if sitemap_url in seen or len(seen) >= max_docs:
        return
    seen.add(sitemap_url)
    try:
        response = get(session, sitemap_url, 30)
        root = ET.fromstring(_xml_bytes(response, sitemap_url))
    except Exception:
        return

    tag = root.tag.lower()
    if tag.endswith("sitemapindex"):
        for child in list(root):
            loc = ""
            for elem in list(child):
                if elem.tag.lower().endswith("loc") and elem.text:
                    loc = elem.text.strip()
                    break
            if loc:
                yield from iter_sitemap_records(session, loc, seen, max_docs=max_docs)
    else:
        for child in list(root):
            loc = ""
            lastmod = ""
            for elem in list(child):
                low = elem.tag.lower()
                if low.endswith("loc") and elem.text:
                    loc = elem.text.strip()
                elif low.endswith("lastmod") and elem.text:
                    lastmod = elem.text.strip()
            if loc:
                yield {"url": loc, "lastmod": lastmod, "sitemap": sitemap_url}
