"""Tests for SQL snapshot boundaries and labels."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from clv_decision_system.features import build_customer_snapshots  # noqa: E402, I001


class FeatureSnapshotTests(unittest.TestCase):
    def setUp(self) -> None:
        self.customers = pd.DataFrame(
            {
                "customer_id": ["C00001", "C00002"],
                "acquisition_date": ["2022-01-01", "2022-01-01"],
                "acquisition_channel": ["organic", "referral"],
                "region": ["north", "south"],
            }
        )
        self.orders = pd.DataFrame(
            {
                "order_id": ["O1", "O2", "O3"],
                "customer_id": ["C00001", "C00001", "C00002"],
                "order_date": ["2023-06-20", "2023-07-10", "2023-07-15"],
                "category": ["home", "beauty", "fashion"],
                "order_channel": ["app", "web", "app"],
                "net_revenue": [100.0, 120.0, 90.0],
                "contribution_margin": [30.0, 40.0, 25.0],
                "discount_ratio": [0.1, 0.0, 0.2],
                "returned": [0, 0, 0],
            }
        )

    def test_future_orders_do_not_enter_features(self) -> None:
        snapshot = build_customer_snapshots(
            self.customers,
            self.orders,
            ["2023-06-30"],
            lookback_days=365,
            horizon_days=180,
            annual_discount_rate=0.1,
            sql_directory=PROJECT_ROOT / "sql",
        )
        customer_one = snapshot.loc[snapshot["customer_id"] == "C00001"].iloc[0]
        self.assertEqual(customer_one["orders_365d"], 1)
        self.assertEqual(customer_one["margin_365d"], 30.0)
        self.assertEqual(customer_one["future_orders_180d"], 1)
        self.assertGreater(customer_one["future_discounted_margin_180d"], 39.0)
        self.assertLess(customer_one["future_discounted_margin_180d"], 40.0)
        self.assertEqual(customer_one["future_active_180d"], 1)

    def test_negative_future_margin_still_counts_as_purchase_activity(self) -> None:
        orders = self.orders.copy()
        orders.loc[orders["order_id"] == "O2", "contribution_margin"] = -40.0
        snapshot = build_customer_snapshots(
            self.customers,
            orders,
            ["2023-06-30"],
            lookback_days=365,
            horizon_days=180,
            annual_discount_rate=0.1,
            sql_directory=PROJECT_ROOT / "sql",
        )
        customer_one = snapshot.loc[snapshot["customer_id"] == "C00001"].iloc[0]
        self.assertLess(customer_one["future_discounted_margin_180d"], 0.0)
        self.assertEqual(customer_one["future_active_180d"], 1)

    def test_snapshot_keys_are_unique(self) -> None:
        snapshot = build_customer_snapshots(
            self.customers,
            self.orders,
            ["2023-06-30"],
            lookback_days=365,
            horizon_days=180,
            annual_discount_rate=0.1,
            sql_directory=PROJECT_ROOT / "sql",
        )
        self.assertFalse(snapshot.duplicated(["customer_id", "snapshot_date"]).any())


if __name__ == "__main__":
    unittest.main()
