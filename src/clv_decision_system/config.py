"""Configuration loading and validation."""

from __future__ import annotations

import json
import math
from datetime import date, timedelta
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
    "bootstrap_iterations",
    "seed",
    "snapshot_dates",
    "lookback_days",
    "horizon_days",
    "selection_snapshot",
    "calibration_snapshot",
    "test_snapshot",
    "interval_target_coverage",
}

REQUIRED_POLICY_KEYS = {
    "tier_shares",
    "investment_fraction",
    "tier_caps",
    "uncertainty_ratio",
}
TIER_NAMES = {"protect", "grow", "nurture", "low_touch"}


def _as_date(value: Any, name: str) -> date:
    try:
        return date.fromisoformat(str(value))
    except ValueError as error:
        raise ValueError(f"{name} must be an ISO date") from error


def _positive_integer(value: Any, name: str, minimum: int = 1) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be an integer")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{name} must be an integer") from error
    if parsed != value or parsed < minimum:
        raise ValueError(f"{name} must be an integer greater than or equal to {minimum}")
    return parsed


def _finite_number(value: Any, name: str) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{name} must be numeric") from error
    if not math.isfinite(parsed):
        raise ValueError(f"{name} must be finite")
    return parsed


def _validate_temporal_splits(config: dict[str, Any], prefix: str = "") -> list[date]:
    snapshots = config["snapshot_dates"]
    if not isinstance(snapshots, list) or len(snapshots) < 4:
        raise ValueError(f"{prefix}At least four temporal snapshots are required")
    parsed_snapshots = [_as_date(value, "snapshot_dates") for value in snapshots]
    if parsed_snapshots != sorted(parsed_snapshots) or len(set(parsed_snapshots)) != len(
        parsed_snapshots
    ):
        raise ValueError(f"{prefix}snapshot_dates must be unique and ordered")

    split_dates = [
        _as_date(config["selection_snapshot"], "selection_snapshot"),
        _as_date(config["calibration_snapshot"], "calibration_snapshot"),
        _as_date(config["test_snapshot"], "test_snapshot"),
    ]
    if any(value not in parsed_snapshots for value in split_dates):
        raise ValueError(f"{prefix}All split snapshots must be listed in snapshot_dates")
    if split_dates != sorted(split_dates) or len(set(split_dates)) != len(split_dates):
        raise ValueError(f"{prefix}selection, calibration, and test snapshots must be ordered")
    if not any(value < split_dates[0] for value in parsed_snapshots):
        raise ValueError(f"{prefix}At least one training snapshot must precede selection")
    return parsed_snapshots


def _validate_policy(policy: Any) -> None:
    if not isinstance(policy, dict):
        raise ValueError("policy must be an object")
    missing = REQUIRED_POLICY_KEYS.difference(policy)
    if missing:
        raise ValueError(f"Missing policy keys: {sorted(missing)}")

    shares = policy["tier_shares"]
    caps = policy["tier_caps"]
    if not isinstance(shares, dict) or set(shares) != TIER_NAMES:
        raise ValueError(f"tier_shares must contain exactly {sorted(TIER_NAMES)}")
    if not isinstance(caps, dict) or set(caps) != TIER_NAMES:
        raise ValueError(f"tier_caps must contain exactly {sorted(TIER_NAMES)}")
    parsed_shares = {
        name: _finite_number(value, f"tier_shares.{name}") for name, value in shares.items()
    }
    if any(value < 0.0 or value > 1.0 for value in parsed_shares.values()):
        raise ValueError("Each tier share must be between zero and one")
    if not math.isclose(sum(parsed_shares.values()), 1.0, rel_tol=0.0, abs_tol=1e-9):
        raise ValueError("Tier shares must sum to one")
    if any(_finite_number(value, f"tier_caps.{name}") < 0.0 for name, value in caps.items()):
        raise ValueError("Tier caps must be non-negative")
    investment_fraction = _finite_number(policy["investment_fraction"], "investment_fraction")
    if not 0.0 <= investment_fraction <= 1.0:
        raise ValueError("investment_fraction must be between zero and one")
    if _finite_number(policy["uncertainty_ratio"], "uncertainty_ratio") <= 0.0:
        raise ValueError("uncertainty_ratio must be positive")


def load_config(path: str | Path) -> dict[str, Any]:
    """Load and validate a pipeline configuration file."""
    config_path = Path(path)
    with config_path.open(encoding="utf-8") as handle:
        config = json.load(handle)

    missing = REQUIRED_TOP_LEVEL_KEYS.difference(config)
    if missing:
        raise ValueError(f"Missing configuration keys: {sorted(missing)}")
    _positive_integer(config["n_customers"], "n_customers", minimum=50)
    snapshots = _validate_temporal_splits(config)
    lookback_days = _positive_integer(config["lookback_days"], "lookback_days", minimum=30)
    horizon_days = _positive_integer(config["horizon_days"], "horizon_days", minimum=30)
    data_start = _as_date(config["data_start"], "data_start")
    data_end = _as_date(config["data_end"], "data_end")
    if data_start >= snapshots[0]:
        raise ValueError("data_start must precede the first snapshot")
    if data_start > snapshots[0] - timedelta(days=lookback_days):
        raise ValueError("data_start must cover the complete first-snapshot lookback")
    test_end = _as_date(config["test_snapshot"], "test_snapshot") + timedelta(days=horizon_days)
    if data_end < test_end:
        raise ValueError("data_end must cover the complete test horizon")
    if lookback_days <= 0:
        raise ValueError("lookback_days must be positive")
    discount_rate = _finite_number(config["annual_discount_rate"], "annual_discount_rate")
    if not 0.0 <= discount_rate <= 1.0:
        raise ValueError("annual_discount_rate must be between zero and one")
    if (
        not 0.0
        < _finite_number(config["interval_target_coverage"], "interval_target_coverage")
        < 1.0
    ):
        raise ValueError("interval_target_coverage must be strictly between zero and one")
    _validate_policy(config["policy"])
    return config


def load_public_validation_config(path: str | Path) -> dict[str, Any]:
    """Load the narrower configuration used by licensed public validation."""
    config_path = Path(path)
    with config_path.open(encoding="utf-8") as handle:
        config = json.load(handle)
    missing = REQUIRED_PUBLIC_KEYS.difference(config)
    if missing:
        raise ValueError(f"Missing public-validation configuration keys: {sorted(missing)}")
    _validate_temporal_splits(config, prefix="Public ")
    if (
        _positive_integer(config["lookback_days"], "lookback_days") < 180
        or _positive_integer(config["horizon_days"], "horizon_days") < 30
    ):
        raise ValueError("Public lookback and horizon windows are too short")
    if (
        not 0.0
        < _finite_number(config["interval_target_coverage"], "interval_target_coverage")
        < 1.0
    ):
        raise ValueError("Public interval target must be strictly between zero and one")
    _positive_integer(config["bootstrap_iterations"], "bootstrap_iterations", minimum=200)
    return config
