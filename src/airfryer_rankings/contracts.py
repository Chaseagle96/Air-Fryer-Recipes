from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

RAW_OBSERVATION_SCHEMA_VERSION = 2
CLEAN_RECIPE_SCHEMA_VERSION = 5
RANKING_SCHEMA_VERSION = 5
SERVING_SCHEMA_VERSION = 4
CONTRACT_MANIFEST_VERSION = 1


@dataclass(frozen=True)
class DataContract:
    name: str
    version: int
    authoritative: bool
    location: str
    description: str


CONTRACTS = (
    DataContract(
        "raw_observation",
        RAW_OBSERVATION_SCHEMA_VERSION,
        True,
        "data/observations/YYYY/MM/DD/*.ndjson",
        "Immutable fetched rating evidence. This is the primary longitudinal source of truth.",
    ),
    DataContract(
        "clean_recipe",
        CLEAN_RECIPE_SCHEMA_VERSION,
        False,
        "data/state.json",
        "Validated current recipe state reconstructed from raw observations and crawler metadata.",
    ),
    DataContract(
        "ranking",
        RANKING_SCHEMA_VERSION,
        False,
        "data/rankings/YYYY/MM/DD/*.ndjson",
        "Versioned model outputs and rank snapshots derived from clean evidence.",
    ),
    DataContract(
        "serving",
        SERVING_SCHEMA_VERSION,
        False,
        "output/, docs/, and docs/api/",
        "Human- and machine-facing CSV, Excel, DuckDB, JSON, web presentation, and paged mobile-feed artifacts.",
    ),
)


def contract_manifest() -> dict:
    return {
        "manifest_version": CONTRACT_MANIFEST_VERSION,
        "contracts": [asdict(contract) for contract in CONTRACTS],
        "lineage": [
            "raw_observation -> clean_recipe",
            "clean_recipe -> ranking",
            "ranking -> serving",
        ],
        "rule": "Derived layers may be rebuilt; immutable raw observations must never be rewritten to match a model output.",
    }


def write_contract_manifest(path: str | Path) -> str:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(contract_manifest(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return str(target)
