from __future__ import annotations

import gzip
import hashlib
import json
import math
import re
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Iterator
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser
from xml.etree import ElementTree as ET

import requests
import yaml
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

UA = "AirFryerRankingsBot/2.0 (+https://github.com/Chaseagle96/Air-Fryer-Recipes; research crawler)"
HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}
KEY_RE = re.compile(r"(?:air[-_ ]?fry(?:er|ing|ed)|airfry(?:er|ing|ed))", re.I)
SPACE_RE = re.compile(r"[^a-z0-9]+")
DEFAULT_STATE = {"recipes": {}, "rank_history": [], "source_history": [], "schema_version": 2}


@dataclass
class RecipeRow:
    recipe_id: str
    title: str
    source: str
    url: str
    rating: float
    rating_count: int
    best_rating: float
    normalized_rating: float
    retrieved_at: str
    author: str = ""
    ingredient_signature: str = ""
    canonical_url: str = ""


@dataclass
class SourceConfig:
    domain: str
    enabled: bool = True
    max_urls: int = 200
    delay: float = 0.20
    sitemap_urls: tuple[str, ...] = ()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_text(value: str) -> str:
    return SPACE_RE.sub(" ", value.lower()).strip()


def ingredient_signature(ingredients: Iterable[str]) -> str:
    normalized = [normalize_text(x) for x in ingredients if normalize_text(x)]
    if not normalized:
        return ""
    payload = "\n".join(sorted(dict.fromkeys(normalized)))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def load_sources(path: str | Path) -> list[SourceConfig]:
    data = yaml.safe_load(Path(path).read_text()) or {}
    out: list[SourceConfig] = []
    defaults = data.get("defaults", {}) or {}
    for item in data.get("sources", []):
        if not item.get("enabled", True):
            continue
        out.append(
            SourceConfig(
                domain=item["domain"].lower().strip(),
                enabled=True,
                max_urls=int(item.get("max_urls", defaults.get("max_urls", 200))),
                delay=float(item.get("delay", defaults.get("delay", 0.20))),
                sitemap_urls=tuple(item.get("sitemap_urls", []) or []),
            )
        )
    return out


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
    session.mount("https://", HTTPAdapter(max_retries=retries))
    session.mount("http://", HTTPAdapter(max_retries=retries))
    return session


def get(session: requests.Session, url: str, timeout: int = 20) -> requests.Response:
    response = session.get(url, headers=HEADERS, timeout=timeout)
    response.raise_for_status()
    return response


def robots_and_sitemaps(session: requests.Session, cfg: SourceConfig) -> tuple[RobotFileParser, list[str], str]:
    robots_url = f"https://{cfg.domain}/robots.txt"
    robots_text = ""
    try:
        robots_text = get(session, robots_url, 15).text
    except Exception:
        pass

    parser = RobotFileParser()
    parser.set_url(robots_url)
    try:
        parser.parse(robots_text.splitlines())
    except Exception:
        parser = RobotFileParser()
        parser.set_url(robots_url)
        parser.parse([])

    sitemaps = list(cfg.sitemap_urls)
    for line in robots_text.splitlines():
        if line.lower().startswith("sitemap:"):
            value = line.split(":", 1)[1].strip()
            if value:
                sitemaps.append(value)
    if not sitemaps:
        sitemaps = [f"https://{cfg.domain}/sitemap.xml"]
    return parser, list(dict.fromkeys(sitemaps)), robots_text


def _xml_bytes(response: requests.Response, url: str) -> bytes:
    content = response.content
    if url.lower().endswith(".gz") or content[:2] == b"\x1f\x8b":
        try:
            return gzip.decompress(content)
        except OSError:
            return content
    return content


def iter_sitemap_urls(
    session: requests.Session,
    sitemap_url: str,
    seen: set[str] | None = None,
    max_docs: int = 150,
) -> Iterator[str]:
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
        for elem in root.iter():
            if elem.tag.lower().endswith("loc") and elem.text:
                child = elem.text.strip()
                if child:
                    yield from iter_sitemap_urls(session, child, seen, max_docs=max_docs)
    else:
        for elem in root.iter():
            if elem.tag.lower().endswith("loc") and elem.text:
                url = elem.text.strip()
                if url:
                    yield url


def jsonld_objects(soup: BeautifulSoup) -> Iterator[dict]:
    for tag in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = tag.string or tag.get_text()
        if not raw:
            continue
        try:
            obj = json.loads(raw)
        except Exception:
            continue
        stack = obj if isinstance(obj, list) else [obj]
        while stack:
            item = stack.pop()
            if isinstance(item, dict):
                yield item
                graph = item.get("@graph")
                if isinstance(graph, list):
                    stack.extend(graph)
                main = item.get("mainEntity")
                if isinstance(main, (dict, list)):
                    stack.extend(main if isinstance(main, list) else [main])
            elif isinstance(item, list):
                stack.extend(item)


def _author_name(obj: dict) -> str:
    author = obj.get("author")
    if isinstance(author, str):
        return author.strip()
    if isinstance(author, dict):
        return str(author.get("name") or "").strip()
    if isinstance(author, list):
        names = []
        for x in author:
            if isinstance(x, str):
                names.append(x.strip())
            elif isinstance(x, dict) and x.get("name"):
                names.append(str(x["name"]).strip())
        return ", ".join(x for x in names if x)
    return ""


def extract_recipe(session: requests.Session, url: str, domain: str) -> RecipeRow | None:
    try:
        html = get(session, url, 25).text
    except Exception:
        return None
    soup = BeautifulSoup(html, "lxml")
    canonical = ""
    canonical_tag = soup.find("link", rel=lambda value: value and "canonical" in str(value).lower())
    if canonical_tag and canonical_tag.get("href"):
        canonical = canonical_tag["href"].strip()

    candidates: list[RecipeRow] = []
    for obj in jsonld_objects(soup):
        typ = obj.get("@type")
        types = typ if isinstance(typ, list) else [typ]
        if "Recipe" not in types:
            continue
        agg = obj.get("aggregateRating") or {}
        if not isinstance(agg, dict):
            continue
        try:
            rating = float(agg.get("ratingValue"))
            count = int(float(agg.get("ratingCount") or agg.get("reviewCount")))
            best = float(agg.get("bestRating") or 5)
        except Exception:
            continue
        if count <= 0 or best <= 0 or rating < 0:
            continue

        title = str(obj.get("name") or (soup.title.string if soup.title else "") or url).strip()
        norm = max(0.0, min(5.0, rating / best * 5.0))
        ingredients = obj.get("recipeIngredient") or []
        if not isinstance(ingredients, list):
            ingredients = []
        sig = ingredient_signature(str(x) for x in ingredients)
        chosen_url = canonical or url
        rid = hashlib.sha256(chosen_url.encode("utf-8")).hexdigest()[:24]
        candidates.append(
            RecipeRow(
                recipe_id=rid,
                title=title,
                source=domain,
                url=url,
                rating=rating,
                rating_count=count,
                best_rating=best,
                normalized_rating=norm,
                retrieved_at=now_iso(),
                author=_author_name(obj),
                ingredient_signature=sig,
                canonical_url=chosen_url,
            )
        )
    if not candidates:
        return None
    return max(candidates, key=lambda r: r.rating_count)


def discover_domain(cfg: SourceConfig, global_max_urls: int | None = None) -> tuple[list[RecipeRow], dict]:
    started = time.monotonic()
    session = make_session()
    parser, sitemaps, _ = robots_and_sitemaps(session, cfg)
    max_urls = min(cfg.max_urls, global_max_urls) if global_max_urls else cfg.max_urls
    seen_sitemaps: set[str] = set()
    candidates: list[str] = []

    for sitemap in sitemaps:
        for url in iter_sitemap_urls(session, sitemap, seen=seen_sitemaps):
            parsed = urlparse(url)
            if not parsed.netloc.lower().endswith(cfg.domain):
                continue
            if not KEY_RE.search(url):
                continue
            try:
                allowed = parser.can_fetch(UA, url)
            except Exception:
                allowed = True
            if not allowed:
                continue
            candidates.append(url)
            if len(candidates) >= max_urls:
                break
        if len(candidates) >= max_urls:
            break

    unique_candidates = list(dict.fromkeys(candidates))
    rows: list[RecipeRow] = []
    for url in unique_candidates:
        row = extract_recipe(session, url, cfg.domain)
        if row:
            rows.append(row)
        if cfg.delay > 0:
            time.sleep(cfg.delay)

    elapsed = round(time.monotonic() - started, 2)
    return rows, {
        "source": cfg.domain,
        "candidate_urls": len(unique_candidates),
        "verified_recipes": len(rows),
        "sitemap_docs": len(seen_sitemaps),
        "elapsed_seconds": elapsed,
        "status": "ok",
    }


def load_state(path: str | Path) -> dict:
    p = Path(path)
    if not p.exists():
        return json.loads(json.dumps(DEFAULT_STATE))
    try:
        state = json.loads(p.read_text())
    except Exception:
        return json.loads(json.dumps(DEFAULT_STATE))
    state.setdefault("recipes", {})
    state.setdefault("rank_history", [])
    state.setdefault("source_history", [])
    state.setdefault("schema_version", 2)
    return state


def save_state(path: str | Path, state: dict) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")


def merge_observations(state: dict, rows: Iterable[RecipeRow], run_at: str) -> None:
    recipes = state.setdefault("recipes", {})
    for row in rows:
        existing = recipes.get(row.recipe_id, {})
        payload = asdict(row)
        payload["first_seen_at"] = existing.get("first_seen_at", run_at)
        payload["last_seen_at"] = run_at
        payload["last_run_at"] = run_at
        payload["previous_rating"] = existing.get("normalized_rating")
        payload["previous_rating_count"] = existing.get("rating_count")
        recipes[row.recipe_id] = payload


def _percentile(values: list[int], q: float) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    if len(values) == 1:
        return float(values[0])
    pos = (len(values) - 1) * q
    lo = math.floor(pos)
    hi = math.ceil(pos)
    if lo == hi:
        return float(values[lo])
    return values[lo] + (values[hi] - values[lo]) * (pos - lo)


def _fresh(recipe: dict, now: datetime, stale_days: int) -> bool:
    raw = recipe.get("last_seen_at") or recipe.get("retrieved_at")
    if not raw:
        return False
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except Exception:
        return False
    return dt >= now - timedelta(days=stale_days)


def _dedupe_key(recipe: dict) -> str:
    title = normalize_text(recipe.get("title", ""))
    sig = recipe.get("ingredient_signature") or ""
    if sig and title:
        return f"sig:{hashlib.sha256((title + '|' + sig).encode()).hexdigest()[:24]}"
    return f"url:{recipe.get('recipe_id')}"


def dedupe_current(recipes: Iterable[dict]) -> tuple[list[dict], int]:
    groups: dict[str, list[dict]] = {}
    for recipe in recipes:
        groups.setdefault(_dedupe_key(recipe), []).append(recipe)

    output: list[dict] = []
    deduped = 0
    for group in groups.values():
        if len(group) == 1:
            item = dict(group[0])
            item["combined_sources"] = item.get("source", "")
            item["combined_urls"] = item.get("canonical_url") or item.get("url", "")
            output.append(item)
            continue

        deduped += len(group) - 1
        total_count = sum(max(0, int(x.get("rating_count", 0))) for x in group)
        if total_count <= 0:
            continue
        avg = sum(float(x.get("normalized_rating", 0)) * int(x.get("rating_count", 0)) for x in group) / total_count
        representative = max(group, key=lambda x: int(x.get("rating_count", 0)))
        item = dict(representative)
        item["normalized_rating"] = avg
        item["rating_count"] = total_count
        item["combined_sources"] = " | ".join(sorted({x.get("source", "") for x in group if x.get("source")}))
        item["combined_urls"] = " | ".join(sorted({x.get("canonical_url") or x.get("url", "") for x in group if x.get("url")}))
        output.append(item)
    return output, deduped


def bayesian_rank(state: dict, stale_days: int = 14, history_limit: int = 168) -> tuple[list[dict], dict]:
    now = datetime.now(timezone.utc)
    current = [dict(x) for x in state.get("recipes", {}).values() if _fresh(x, now, stale_days) and int(x.get("rating_count", 0)) > 0]
    current, deduped = dedupe_current(current)
    if not current:
        return [], {"global_prior": 0.0, "volume_prior_m": 0.0, "candidate_count": 0, "deduplicated_count": deduped}

    counts = [int(x["rating_count"]) for x in current]
    weights = [math.sqrt(max(1, c)) for c in counts]
    ratings = [float(x["normalized_rating"]) for x in current]
    C = sum(r * w for r, w in zip(ratings, weights)) / sum(weights)
    m = max(50.0, _percentile(counts, 0.60))

    previous_snapshot = state.get("rank_history", [])[-1] if state.get("rank_history") else None
    prev = {x["recipe_id"]: int(x["rank"]) for x in (previous_snapshot or {}).get("top50", [])}

    ranked: list[dict] = []
    for item in current:
        v = int(item["rating_count"])
        R = float(item["normalized_rating"])
        score = (v / (v + m)) * R + (m / (v + m)) * C
        ranked.append(
            {
                "recipe_id": item["recipe_id"],
                "title": item["title"],
                "source": item.get("source", ""),
                "combined_sources": item.get("combined_sources", item.get("source", "")),
                "url": item.get("canonical_url") or item.get("url", ""),
                "rating": R,
                "rating_count": v,
                "bayesian_score": score,
                "author": item.get("author", ""),
                "last_seen_at": item.get("last_seen_at", ""),
                "rating_change": None if item.get("previous_rating") is None else R - float(item.get("previous_rating")),
                "review_count_change": None if item.get("previous_rating_count") is None else v - int(item.get("previous_rating_count")),
            }
        )

    ranked.sort(key=lambda x: (x["bayesian_score"], math.log1p(x["rating_count"])), reverse=True)
    for idx, row in enumerate(ranked, 1):
        row["rank"] = idx
        row["previous_rank"] = prev.get(row["recipe_id"])
        row["movement"] = prev[row["recipe_id"]] - idx if row["recipe_id"] in prev else None

    run_at = now_iso()
    snapshot = {
        "run_at": run_at,
        "top50": [
            {
                "recipe_id": x["recipe_id"],
                "rank": x["rank"],
                "bayesian_score": round(x["bayesian_score"], 8),
                "rating": x["rating"],
                "rating_count": x["rating_count"],
            }
            for x in ranked[:50]
        ],
    }
    history = state.setdefault("rank_history", [])
    history.append(snapshot)
    if len(history) > history_limit:
        del history[:-history_limit]

    return ranked, {
        "global_prior": C,
        "volume_prior_m": m,
        "candidate_count": len(current),
        "deduplicated_count": deduped,
        "stale_days": stale_days,
        "history_snapshots": len(history),
    }
