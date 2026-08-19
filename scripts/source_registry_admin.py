from __future__ import annotations

import argparse
import json
from pathlib import Path

from airfryer_rankings.source_registry import apply_manual_override, load_source_registry, save_source_registry

VERTICALS = {
    "air_fryer": Path("data/source_registry.json"),
    "slow_cooker": Path("verticals/slow_cooker/data/source_registry.json"),
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply an auditable Recipe Intelligence source override")
    parser.add_argument("vertical", choices=tuple(VERTICALS))
    parser.add_argument("action", choices=("approve", "reject", "block", "pin", "suspend", "restore"))
    parser.add_argument("domain")
    parser.add_argument("--reason", required=True)
    parser.add_argument("--registry", default=None, help="Optional registry path override")
    args = parser.parse_args()

    path = Path(args.registry) if args.registry else VERTICALS[args.vertical]
    registry = load_source_registry(path, args.vertical)
    record = apply_manual_override(
        registry,
        args.domain,
        args.action,
        reason=args.reason,
    )
    save_source_registry(path, registry)
    print(json.dumps(record, indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
