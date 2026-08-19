from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml

from airfryer_rankings.models import now_iso
from airfryer_rankings.source_hygiene import retire_nonpublisher_candidates
from airfryer_rankings.source_registry import load_source_registry, save_source_registry
from airfryer_rankings.storage import write_run_records


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit-retire non-publisher source candidates")
    parser.add_argument("--config", default="config/source_discovery.yaml")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    config_path = Path(args.config)
    config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    blocked = [str(value) for value in config.get("blocked_domain_suffixes", [])]
    timestamp = now_iso()
    summary: dict[str, int] = {}

    for vertical, item in (config.get("verticals", {}) or {}).items():
        if not isinstance(item, dict):
            continue
        registry_path = Path(str(item["registry_path"]))
        events_dir = Path(str(item["events_dir"]))
        registry = load_source_registry(registry_path, str(vertical))
        audit_start = len(registry.get("audit", []))
        retired = retire_nonpublisher_candidates(
            registry,
            blocked_suffixes=blocked,
            timestamp=timestamp,
        )
        summary[str(vertical)] = retired
        if args.dry_run or retired == 0:
            continue
        save_source_registry(registry_path, registry)
        new_events = registry.get("audit", [])[audit_start:]
        write_run_records(events_dir, new_events, timestamp)

    print(json.dumps({"generated_at": timestamp, "retired": summary, "dry_run": args.dry_run}, sort_keys=True))


if __name__ == "__main__":
    main()
