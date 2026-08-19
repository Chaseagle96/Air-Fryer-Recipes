from __future__ import annotations

import argparse
import json

from airfryer_rankings.source_catalog_sync import sync_promoted_source_catalogs


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed auto-promoted Recipe Intelligence publishers into URL catalogs")
    parser.add_argument("--config", default="config/source_discovery.yaml")
    parser.add_argument("--mode", choices=("auto", "daily", "deep"), default="auto")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    result = sync_promoted_source_catalogs(args.config, mode=args.mode, dry_run=args.dry_run)
    print(json.dumps(result, indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
