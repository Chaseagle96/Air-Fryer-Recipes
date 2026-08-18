from __future__ import annotations

import time
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from .http import get, iter_sitemap_records, make_session, robots_and_sitemaps
from .models import KEY_RE, UA, SourceConfig

def _catalog_update(state: dict, cfg: SourceConfig, url: str, run_at: str, *, lastmod: str = "", method: str = "sitemap") -> bool:
    catalog = state.setdefault("url_catalog", {})
    existing = catalog.get(url, {})
    is_new = not bool(existing)
    changed_lastmod = bool(lastmod and existing.get("lastmod") and lastmod != existing.get("lastmod"))
    entry = dict(existing)
    entry.update(
        {
            "url": url,
            "source": cfg.domain,
            "lastmod": lastmod or existing.get("lastmod", ""),
            "first_discovered": existing.get("first_discovered", run_at),
            "last_discovered": run_at,
            "discovery_method": method,
        }
    )
    if changed_lastmod:
        entry["priority"] = "modified"
    elif is_new:
        entry["priority"] = "new"
    catalog[url] = entry
    return is_new


def _same_domain(url: str, domain: str) -> bool:
    host = urlparse(url).netloc.lower().split(":")[0]
    return host == domain or host.endswith("." + domain)


def _looks_recipe_link(url: str, text: str, domain: str) -> bool:
    if not _same_domain(url, domain):
        return False
    parsed = urlparse(url)
    path = parsed.path.lower()
    if path in ("", "/") or any(x in path for x in ("/category/", "/tag/", "/author/", "/about", "/contact", "/privacy")):
        return False
    if KEY_RE.search(url + " " + text):
        return True
    # Category discovery pages may link to air-fryer recipes whose slugs omit the cooking method.
    return path.count("/") >= 2 and not path.endswith((".jpg", ".jpeg", ".png", ".webp", ".pdf"))


def discover_source_urls(
    cfg: SourceConfig,
    state: dict,
    mode: str,
    run_at: str,
    global_max_urls: int | None = None,
) -> dict:
    started = time.monotonic()
    session = make_session()
    parser, sitemaps, _, robots_status = robots_and_sitemaps(session, cfg)
    seen_sitemaps: set[str] = set()
    max_docs = 300 if mode == "deep" else 120
    matched = 0
    newly_discovered = 0
    discovery_page_links = 0
    match_cap = 20000 if mode == "deep" and global_max_urls is None else max(2000, (global_max_urls or cfg.max_urls) * (12 if mode == "deep" else 6))

    for sitemap in sitemaps:
        for record in iter_sitemap_records(session, sitemap, seen=seen_sitemaps, max_docs=max_docs):
            url = record["url"]
            if not _same_domain(url, cfg.domain) or not KEY_RE.search(url):
                continue
            try:
                if not parser.can_fetch(UA, url):
                    continue
            except Exception:
                pass
            newly_discovered += int(_catalog_update(state, cfg, url, run_at, lastmod=record.get("lastmod", ""), method="sitemap"))
            matched += 1
            if matched >= match_cap:
                break
        if matched >= match_cap:
            break

    for discovery_url in cfg.discovery_urls:
        try:
            if not parser.can_fetch(UA, discovery_url):
                continue
        except Exception:
            pass
        try:
            response = get(session, discovery_url, 25)
            soup = BeautifulSoup(response.text, "lxml")
        except Exception:
            continue
        for anchor in soup.find_all("a", href=True):
            href = urljoin(discovery_url, str(anchor.get("href") or "").strip())
            text = anchor.get_text(" ", strip=True)
            if not _looks_recipe_link(href, text, cfg.domain):
                continue
            href = href.split("#", 1)[0]
            newly_discovered += int(_catalog_update(state, cfg, href, run_at, method="category"))
            discovery_page_links += 1

    return {
        "source": cfg.domain,
        "discovered_urls": matched + discovery_page_links,
        "new_urls": newly_discovered,
        "sitemap_docs": len(seen_sitemaps),
        "robots_status": robots_status,
        "elapsed_seconds": round(time.monotonic() - started, 2),
        "status": "ok",
    }
