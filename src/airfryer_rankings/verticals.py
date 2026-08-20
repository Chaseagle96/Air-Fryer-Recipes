"""Canonical vertical definitions loaded from source discovery configuration."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class VerticalDefinition:
    id: str
    name: str
    root_path: Path
    source_config_path: Path
    model_config_path: Path
    storage_config_path: Path
    state_path: Path
    registry_path: Path
    output_root: Path
    events_root: Path
    docs_root: Path
    manifest_path: Path
    authority_path: Path
    public_authority_path: Path
    summary_path: Path
    include_pattern: str
    allow_unmatched_discovery_links: bool


def _root(config_path: Path) -> Path:
    return config_path.resolve().parent.parent


def _path(root: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def _definition(root: Path, slug: str, item: dict[str, Any]) -> VerticalDefinition:
    return VerticalDefinition(
        id=slug,
        name=str(item.get("name") or slug.replace("_", " ").title()),
        root_path=_path(root, str(item.get("root_path", "."))),
        source_config_path=_path(root, str(item["base_sources_path"])),
        model_config_path=_path(root, str(item.get("model_config_path", "config/model.yaml"))),
        storage_config_path=_path(root, str(item["storage_config_path"])),
        state_path=_path(root, str(item["state_path"])),
        registry_path=_path(root, str(item["registry_path"])),
        output_root=_path(root, str(item["output_dir"])),
        events_root=_path(root, str(item["events_dir"])),
        docs_root=_path(root, str(item["docs_root"])),
        manifest_path=_path(root, str(item["manifest_path"])),
        authority_path=_path(root, str(item["authority_path"])),
        public_authority_path=_path(root, str(item["public_authority_path"])),
        summary_path=_path(root, str(item["summary_path"])),
        include_pattern=str(item["include_pattern"]),
        allow_unmatched_discovery_links=bool(item.get("allow_unmatched_discovery_links", False)),
    )


def load_verticals(config_path: str | Path = "config/source_discovery.yaml") -> dict[str, VerticalDefinition]:
    path = Path(config_path)
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    items = payload.get("verticals") if isinstance(payload, dict) else None
    if not isinstance(items, dict) or not items:
        raise ValueError(f"source discovery config must define verticals: {path}")
    root = _root(path)
    if any(not isinstance(item, dict) for item in items.values()):
        raise ValueError(f"vertical definitions must be mappings: {path}")
    return {str(slug): _definition(root, str(slug), item) for slug, item in items.items()}


def get_vertical(slug: str, config_path: str | Path = "config/source_discovery.yaml") -> VerticalDefinition:
    canonical = str(slug).strip().lower().replace("-", "_")
    vertical = load_verticals(config_path).get(canonical)
    if vertical is None:
        available = ", ".join(sorted(load_verticals(config_path)))
        raise ValueError(f"unknown vertical {slug!r}; expected one of: {available}")
    return vertical

