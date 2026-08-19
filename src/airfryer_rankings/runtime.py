from __future__ import annotations

import os
import re
from pathlib import Path


def vertical_name() -> str:
    return (os.getenv("RECIPE_INTELLIGENCE_VERTICAL") or "Air Fryer").strip() or "Air Fryer"


def vertical_slug() -> str:
    configured = (os.getenv("RECIPE_INTELLIGENCE_VERTICAL_SLUG") or "").strip().lower()
    if configured:
        return re.sub(r"[^a-z0-9]+", "_", configured).strip("_") or "air_fryer"
    return re.sub(r"[^a-z0-9]+", "_", vertical_name().lower()).strip("_") or "air_fryer"


def vertical_output_path(path: str | Path, air_fryer_filename: str, suffix: str) -> Path:
    target = Path(path)
    slug = vertical_slug()
    if slug == "air_fryer" or target.name != air_fryer_filename:
        return target
    return target.with_name(f"{slug}_{suffix}")
