"""Configuration loading and validation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

REQUIRED_TOP_LEVEL_KEYS = {
    "seed",
    "n_customers",
    "data_start",
    "data_end",
    "snapshot_dates",
    "lookback_days",
    "horizon_days",
    "annual_discount_rate",
    "validation_snapshot",
    "test_snapshot",
    "policy",
}


def load_config(path: str | Path) -> dict[str, Any]:
    """Load and validate a pipeline configuration file."""
    config_path = Path(path)
    with config_path.open(encoding="utf-8") as handle:
        config = json.load(handle)

    missing = REQUIRED_TOP_LEVEL_KEYS.difference(config)
    if missing:
        raise ValueError(f"Missing configuration keys: {sorted(missing)}")
    if config["n_customers"] < 50:
        raise ValueError("n_customers must be at least 50")
    if len(config["snapshot_dates"]) < 4:
        raise ValueError("At least four temporal snapshots are required")
    if config["validation_snapshot"] not in config["snapshot_dates"]:
        raise ValueError("validation_snapshot must be listed in snapshot_dates")
    if config["test_snapshot"] not in config["snapshot_dates"]:
        raise ValueError("test_snapshot must be listed in snapshot_dates")
    return config
