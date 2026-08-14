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
    "selection_snapshot",
    "calibration_snapshot",
    "test_snapshot",
    "interval_target_coverage",
    "policy",
}

REQUIRED_PUBLIC_KEYS = {
    "seed",
    "snapshot_dates",
    "lookback_days",
    "horizon_days",
    "selection_snapshot",
    "calibration_snapshot",
    "test_snapshot",
    "interval_target_coverage",
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
    split_dates = [
        config["selection_snapshot"],
        config["calibration_snapshot"],
        config["test_snapshot"],
    ]
    if any(date not in config["snapshot_dates"] for date in split_dates):
        raise ValueError("All split snapshots must be listed in snapshot_dates")
    if split_dates != sorted(split_dates) or len(set(split_dates)) != len(split_dates):
        raise ValueError("selection, calibration, and test snapshots must be ordered")
    if not 0.0 < float(config["interval_target_coverage"]) < 1.0:
        raise ValueError("interval_target_coverage must be strictly between zero and one")
    return config


def load_public_validation_config(path: str | Path) -> dict[str, Any]:
    """Load the narrower configuration used by licensed public validation."""
    config_path = Path(path)
    with config_path.open(encoding="utf-8") as handle:
        config = json.load(handle)
    missing = REQUIRED_PUBLIC_KEYS.difference(config)
    if missing:
        raise ValueError(f"Missing public-validation configuration keys: {sorted(missing)}")
    if len(config["snapshot_dates"]) < 4:
        raise ValueError("Public validation requires at least four temporal snapshots")
    split_dates = [
        config["selection_snapshot"],
        config["calibration_snapshot"],
        config["test_snapshot"],
    ]
    if any(date not in config["snapshot_dates"] for date in split_dates):
        raise ValueError("Public split snapshots must be listed in snapshot_dates")
    if split_dates != sorted(split_dates) or len(set(split_dates)) != len(split_dates):
        raise ValueError("Public selection, calibration, and test snapshots must be ordered")
    if int(config["lookback_days"]) < 180 or int(config["horizon_days"]) < 30:
        raise ValueError("Public lookback and horizon windows are too short")
    if not 0.0 < float(config["interval_target_coverage"]) < 1.0:
        raise ValueError("Public interval target must be strictly between zero and one")
    return config
