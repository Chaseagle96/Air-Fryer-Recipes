from __future__ import annotations

import argparse
import json
from pathlib import Path

from bs4 import BeautifulSoup

from .evidence import jsonld_objects
from .http import get, make_session, robots_and_sitemaps
from .models import UA, SourceConfig, load_sources
from .storage import load_state

FIXTURE_JSONLD_FIELDS = {
    "@context",
    "@type",
    "name",
    "author",
    "aggregateRating",
    "recipeIngredient",
    "recipeInstructions",
    "image",
}


def _reduced_recipe_jsonld(soup: BeautifulSoup) -> list[dict]:
    recipes: list[dict] = []
    for obj in jsonld_objects(soup):
        raw_type = obj.get("@type")
        types = raw_type if isinstance(raw_type, list) else [raw_type]
        if not any(str(value).lower() == "recipe" for value in types if value is not None):
            continue
        reduced = {key: obj[key] for key in FIXTURE_JSONLD_FIELDS if key in obj}
        ingredients = reduced.get("recipeIngredient")
        if isinstance(ingredients, list):
            reduced["recipeIngredient"] = ingredients[:8]
        instructions = reduced.get("recipeInstructions")
        if isinstance(instructions, list):
            reduced["recipeInstructions"] = instructions[:4]
        recipes.append(reduced)
    return recipes[:2]


def sanitize_fixture_html(html: str, source_url: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    title = soup.title.get_text(" ", strip=True) if soup.title else "Air Fryer Fixture"
    canonical = soup.find("link", rel=lambda value: value and "canonical" in value)
    canonical_href = canonical.get("href") if canonical else source_url
    jsonld = _reduced_recipe_jsonld(soup)
    visible_nodes = []
    for selector in ('[itemprop="ratingValue"]', '[itemprop="ratingCount"]', '[itemprop="reviewCount"]'):
        for node in soup.select(selector)[:2]:
            visible_nodes.append(str(node))
    parts = [
        "<!doctype html>",
        "<html><head>",
        f"<title>{title}</title>",
        f'<link rel="canonical" href="{canonical_href}">',
    ]
    for obj in jsonld:
        parts.append('<script type="application/ld+json">')
        parts.append(json.dumps(obj, ensure_ascii=False, separators=(",", ":")))
        parts.append("</script>")
    parts.extend(["</head><body>", *visible_nodes, "</body></html>"])
    return "\n".join(parts) + "\n"


def _representative_urls(state: dict, sources: list[SourceConfig]) -> dict[str, str]:
    by_source: dict[str, list[dict]] = {}
    for recipe in state.get("recipes", {}).values():
        source = str(recipe.get("source") or "")
        if source:
            by_source.setdefault(source, []).append(recipe)
    result: dict[str, str] = {}
    for cfg in sources:
        candidates = by_source.get(cfg.domain, [])
        if not candidates:
            continue
        representative = max(candidates, key=lambda row: int(row.get("rating_count", 0) or 0))
        url = representative.get("canonical_url") or representative.get("url")
        if url:
            result[cfg.domain] = str(url)
    return result


def capture_candidate_fixtures(
    sources_path: str,
    state_path: str,
    output_dir: str,
    max_sources: int | None = None,
) -> dict:
    sources = load_sources(sources_path)
    if max_sources is not None:
        sources = sources[:max_sources]
    state = load_state(state_path)
    representative_urls = _representative_urls(state, sources)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    manifest = {"captured": [], "failed": [], "missing_representative": []}
    for cfg in sources:
        url = representative_urls.get(cfg.domain)
        if not url:
            manifest["missing_representative"].append(cfg.domain)
            continue
        session = make_session()
        parser, _, _, _ = robots_and_sitemaps(session, cfg)
        try:
            if not parser.can_fetch(UA, url):
                manifest["failed"].append({"source": cfg.domain, "url": url, "reason": "robots_denied"})
                continue
        except Exception:
            pass
        try:
            response = get(session, url, 25)
            sanitized = sanitize_fixture_html(response.text, url)
            path = output / f"{cfg.domain.replace('.', '_')}.html"
            path.write_text(sanitized, encoding="utf-8")
            manifest["captured"].append({"source": cfg.domain, "url": url, "fixture": path.name})
        except Exception as exc:
            manifest["failed"].append({"source": cfg.domain, "url": url, "reason": type(exc).__name__})
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Capture sanitized candidate regression fixtures from live publisher pages")
    parser.add_argument("--sources", default="config/sources.yaml")
    parser.add_argument("--state", default="data/state.json")
    parser.add_argument("--output", default="output/fixture_candidates")
    parser.add_argument("--max-sources", type=int, default=None)
    args = parser.parse_args()
    result = capture_candidate_fixtures(args.sources, args.state, args.output, args.max_sources)
    print(json.dumps({key: len(value) for key, value in result.items()}, sort_keys=True))


if __name__ == "__main__":
    main()
