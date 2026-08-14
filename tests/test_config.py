"""Tests for configuration validation."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from clv_decision_system.config import (  # noqa: E402, I001
    load_config,
    load_public_validation_config,
)
from clv_decision_system.pipeline import _split_snapshots  # noqa: E402, I001


class ConfigTests(unittest.TestCase):
    def setUp(self) -> None:
        self.valid_config = {
            "seed": 42,
            "n_customers": 100,
            "data_start": "2022-01-01",
            "data_end": "2025-06-30",
            "snapshot_dates": ["2023-01-01", "2023-07-01", "2024-01-01", "2024-07-01"],
            "lookback_days": 365,
            "horizon_days": 180,
            "annual_discount_rate": 0.1,
            "selection_snapshot": "2023-07-01",
            "calibration_snapshot": "2024-01-01",
            "test_snapshot": "2024-07-01",
            "interval_target_coverage": 0.8,
            "policy": {},
        }

    def _write_config(self, config: dict[str, object]) -> Path:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as temporary:
            json.dump(config, temporary)
            path = Path(temporary.name)
        self.addCleanup(path.unlink, missing_ok=True)
        return path

    def test_loads_valid_config(self) -> None:
        result = load_config(self._write_config(self.valid_config))
        self.assertEqual(result["seed"], 42)

    def test_rejects_missing_key(self) -> None:
        invalid = self.valid_config.copy()
        invalid.pop("horizon_days")
        with self.assertRaisesRegex(ValueError, "Missing configuration keys"):
            load_config(self._write_config(invalid))

    def test_rejects_too_few_customers(self) -> None:
        invalid = {**self.valid_config, "n_customers": 49}
        with self.assertRaisesRegex(ValueError, "at least 50"):
            load_config(self._write_config(invalid))

    def test_rejects_misordered_temporal_snapshots(self) -> None:
        invalid = {
            **self.valid_config,
            "selection_snapshot": "2024-01-01",
            "calibration_snapshot": "2023-07-01",
        }
        with self.assertRaisesRegex(ValueError, "must be ordered"):
            load_config(self._write_config(invalid))

    def test_rejects_invalid_interval_target(self) -> None:
        invalid = {**self.valid_config, "interval_target_coverage": 1.0}
        with self.assertRaisesRegex(ValueError, "strictly between"):
            load_config(self._write_config(invalid))

    def test_temporal_split_keeps_calibration_before_test(self) -> None:
        snapshots = pd.DataFrame(
            {
                "snapshot_date": ["2023-01-01", "2023-07-01", "2024-01-01", "2024-07-01"],
                "customer_id": ["C1"] * 4,
            }
        )
        train, selection, calibration, test = _split_snapshots(
            snapshots,
            selection_snapshot="2023-07-01",
            calibration_snapshot="2024-01-01",
            test_snapshot="2024-07-01",
        )
        self.assertLess(train["snapshot_date"].max(), selection["snapshot_date"].min())
        self.assertLess(selection["snapshot_date"].max(), calibration["snapshot_date"].min())
        self.assertLess(calibration["snapshot_date"].max(), test["snapshot_date"].min())

    def test_public_config_is_validated_independently(self) -> None:
        public_config = {
            "seed": 42,
            "snapshot_dates": ["2020-01-01", "2020-04-01", "2020-07-01", "2020-10-01"],
            "lookback_days": 365,
            "horizon_days": 180,
            "selection_snapshot": "2020-04-01",
            "calibration_snapshot": "2020-07-01",
            "test_snapshot": "2020-10-01",
            "interval_target_coverage": 0.8,
        }
        result = load_public_validation_config(self._write_config(public_config))
        self.assertEqual(result["horizon_days"], 180)


if __name__ == "__main__":
    unittest.main()
