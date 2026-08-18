from __future__ import annotations

import hashlib

from bs4 import BeautifulSoup

from .evidence import (
    _author_name,
    _canonical_url,
    _evidence_score,
    _image_url,
    _instruction_texts,
    _parse_histogram,
    _parse_number,
    jsonld_objects,
    visible_rating_evidence,
)
from .models import (
    RecipeRow,
    SourceConfig,
    categorize_recipe,
    fingerprint_image_url,
    ingredient_signature,
    instruction_signature,
    now_iso,
)

def extract_recipe_from_html(
    html: str,
    url: str,
    domain: str,
    cfg: SourceConfig | None = None,
    response_headers: dict | None = None,
) -> tuple[RecipeRow | None, dict]:
    cfg = cfg or SourceConfig(domain=domain)
    response_headers = response_headers or {}
    soup = BeautifulSoup(html, "lxml")
    canonical = _canonical_url(soup, url)
    visible_rating, visible_count = visible_rating_evidence(soup, cfg)
    page_hash = hashlib.sha256(html.encode("utf-8", errors="ignore")).hexdigest()[:24]
    parse_meta = {"issues": [], "page_hash": page_hash}
    candidates: list[RecipeRow] = []

    for obj in jsonld_objects(soup):
        typ = obj.get("@type")
        types = typ if isinstance(typ, list) else [typ]
        if not any(str(x).lower() == "recipe" for x in types if x is not None):
            continue
        agg = obj.get("aggregateRating") or {}
        if not isinstance(agg, dict):
            continue
        rating = _parse_number(agg.get("ratingValue"))
        count_value = _parse_number(agg.get("ratingCount") or agg.get("reviewCount"))
        best = _parse_number(agg.get("bestRating")) or 5.0
        if rating is None or count_value is None:
            continue
        count = int(count_value)
        if count <= 0 or best <= 0 or rating < 0 or rating > best * 1.05:
            parse_meta["issues"].append("malformed_rating_scale")
            continue

        norm = max(0.0, min(5.0, rating / best * 5.0))
        visible_norm = None
        if visible_rating is not None:
            visible_norm = visible_rating if visible_rating <= 5.05 else visible_rating / best * 5.0
        confidence, evidence_status, method = _evidence_score(norm, count, visible_norm, visible_count)
        histogram = _parse_histogram(agg)
        if evidence_status == "conflict":
            parse_meta["issues"].append("rating_evidence_conflict")

        ingredients_raw = obj.get("recipeIngredient") or []
        ingredients = tuple(str(x).strip() for x in ingredients_raw) if isinstance(ingredients_raw, list) else ()
        instructions = _instruction_texts(obj)
        image = _image_url(obj)
        title = str(obj.get("name") or (soup.title.string if soup.title else "") or url).strip()
        rid = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:24]
        candidates.append(
            RecipeRow(
                recipe_id=rid,
                title=title,
                source=domain,
                url=url,
                rating=float(rating),
                rating_count=count,
                best_rating=float(best),
                normalized_rating=norm,
                retrieved_at=now_iso(),
                author=_author_name(obj),
                ingredient_signature=ingredient_signature(ingredients),
                canonical_url=canonical,
                ingredients=ingredients,
                instruction_signature=instruction_signature(instructions),
                instructions=instructions,
                image_url=image,
                image_fingerprint=fingerprint_image_url(image),
                extraction_method=method,
                evidence_confidence=confidence,
                evidence_status=evidence_status,
                page_hash=page_hash,
                etag=str(response_headers.get("ETag") or response_headers.get("etag") or ""),
                last_modified=str(response_headers.get("Last-Modified") or response_headers.get("last-modified") or ""),
                schema_rating=norm,
                schema_rating_count=count,
                visible_rating=visible_norm,
                visible_rating_count=visible_count,
                rating_histogram=histogram,
                categories=categorize_recipe(title, ingredients),
            )
        )

    if candidates:
        return max(candidates, key=lambda r: (r.evidence_confidence, r.rating_count)), parse_meta

    if visible_rating is not None and visible_count and 0 <= visible_rating <= 5.05:
        title = str((soup.title.string if soup.title else "") or url).strip()
        rid = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:24]
        return (
            RecipeRow(
                recipe_id=rid,
                title=title,
                source=domain,
                url=url,
                rating=float(visible_rating),
                rating_count=int(visible_count),
                best_rating=5.0,
                normalized_rating=float(visible_rating),
                retrieved_at=now_iso(),
                canonical_url=canonical,
                extraction_method="visible_microdata",
                evidence_confidence=0.65,
                evidence_status="visible_only",
                page_hash=page_hash,
                etag=str(response_headers.get("ETag") or response_headers.get("etag") or ""),
                last_modified=str(response_headers.get("Last-Modified") or response_headers.get("last-modified") or ""),
                visible_rating=float(visible_rating),
                visible_rating_count=int(visible_count),
                categories=categorize_recipe(title),
            ),
            parse_meta,
        )
    return None, parse_meta
