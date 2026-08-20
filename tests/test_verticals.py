from __future__ import annotations

from pathlib import Path

import pytest

from airfryer_rankings.verticals import get_vertical, load_verticals

CONFIG = Path("config/source_discovery.yaml")


def test_vertical_registry_resolves_both_verticals_with_isolated_state() -> None:
    verticals = load_verticals(CONFIG)
    air_fryer = get_vertical("air-fryer", CONFIG)
    slow_cooker = get_vertical("slow_cooker", CONFIG)

    assert set(verticals) == {"air_fryer", "slow_cooker"}
    assert air_fryer.name == "Air Fryer"
    assert slow_cooker.name == "Slow Cooker"
    assert air_fryer.state_path != slow_cooker.state_path
    assert air_fryer.registry_path != slow_cooker.registry_path
    assert air_fryer.output_root != slow_cooker.output_root
    assert air_fryer.manifest_path != slow_cooker.manifest_path


def test_unknown_vertical_fails_without_fallback() -> None:
    with pytest.raises(ValueError, match="unknown vertical"):
        get_vertical("deep-fryer", CONFIG)
