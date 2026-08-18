"""Tests for deterministic and safe synthetic data."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from clv_decision_system.synthetic import (  # noqa: E402, I001
    generate_customers,
    generate_orders,
    public_customer_columns,
)


class SyntheticDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.customers = generate_customers(80, seed=11)
        cls.orders = generate_orders(cls.customers, "2023-01-01", "2023-12-31", seed=11)

    def test_customer_generation_is_deterministic(self) -> None:
        repeated = generate_customers(80, seed=11)
        pd.testing.assert_frame_equal(self.customers, repeated)

    def test_order_generation_is_deterministic(self) -> None:
        repeated = generate_orders(self.customers, "2023-01-01", "2023-12-31", seed=11)
        pd.testing.assert_frame_equal(self.orders, repeated)

    def test_public_customer_data_excludes_latent_fields(self) -> None:
        public = public_customer_columns(self.customers)
        self.assertFalse(any(column.startswith("_") for column in public.columns))

    def test_orders_have_valid_bounds_and_unique_ids(self) -> None:
        self.assertTrue(self.orders["order_id"].is_unique)
        self.assertTrue((self.orders["contribution_margin"] < 0).any())
        dates = pd.to_datetime(self.orders["order_date"])
        self.assertGreaterEqual(dates.min(), pd.Timestamp("2023-01-01"))
        self.assertLessEqual(dates.max(), pd.Timestamp("2023-12-31"))


if __name__ == "__main__":
    unittest.main()
