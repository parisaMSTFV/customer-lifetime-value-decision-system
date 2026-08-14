"""Tests for DuckDB public snapshots and SQL/Pandas parity."""

from __future__ import annotations

import sys
import unittest
from io import StringIO
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from clv_decision_system.public_features import (  # noqa: E402, I001
    PUBLIC_FEATURES,
    build_public_customer_snapshots,
    build_public_customer_snapshots_pandas,
    public_snapshot_fingerprint,
)


def transaction_fixture() -> pd.DataFrame:
    rows = [
        ("A1", "P1", 2, "2020-01-01 10:00", 10.0, "1", "UK", False, 20.0),
        ("A2", "P2", 1, "2020-03-15 10:00", 30.0, "1", "UK", False, 30.0),
        ("C3", "P2", -1, "2020-03-20 10:00", 5.0, "1", "UK", True, -5.0),
        ("A4", "P3", 1, "2020-04-01 00:00", 40.0, "1", "UK", False, 40.0),
        ("A5", "P4", 1, "2020-05-01 10:00", 50.0, "1", "UK", False, 50.0),
        ("B1", "P1", 1, "2020-02-01 10:00", 15.0, "2", "France", False, 15.0),
        ("B2", "P2", 1, "2020-06-01 10:00", 20.0, "2", "France", False, 20.0),
    ]
    return pd.DataFrame(
        rows,
        columns=[
            "invoice_id",
            "stock_code",
            "quantity",
            "invoice_date",
            "unit_price",
            "customer_id",
            "country",
            "is_cancellation",
            "signed_revenue",
        ],
    ).assign(
        source_sheet="fixture",
        invoice_date=lambda frame: pd.to_datetime(frame["invoice_date"]),
    )


class PublicFeatureTests(unittest.TestCase):
    def test_sql_matches_hand_checkable_pandas_reference(self) -> None:
        transactions = transaction_fixture()
        parameters = {
            "snapshot_dates": ["2020-04-01"],
            "lookback_days": 365,
            "horizon_days": 90,
        }
        sql = build_public_customer_snapshots(
            transactions,
            sql_directory=PROJECT_ROOT / "sql",
            **parameters,
        )
        reference = build_public_customer_snapshots_pandas(transactions, **parameters)
        pd.testing.assert_frame_equal(
            sql.sort_index(axis=1),
            reference.sort_index(axis=1),
            check_dtype=False,
            check_exact=False,
            rtol=1e-10,
        )

    def test_scoring_day_transactions_are_future_not_features(self) -> None:
        snapshot = build_public_customer_snapshots(
            transaction_fixture(),
            ["2020-04-01"],
            lookback_days=365,
            horizon_days=90,
            sql_directory=PROJECT_ROOT / "sql",
        )
        customer = snapshot.loc[snapshot["customer_id"] == "1"].iloc[0]
        self.assertEqual(customer["orders_365d"], 2)
        self.assertEqual(customer["net_revenue_365d"], 45.0)
        self.assertEqual(customer["future_net_revenue_180d"], 90.0)

    def test_all_public_model_features_are_numeric_or_declared_country(self) -> None:
        snapshot = build_public_customer_snapshots(
            transaction_fixture(),
            ["2020-04-01"],
            lookback_days=365,
            horizon_days=90,
            sql_directory=PROJECT_ROOT / "sql",
        )
        self.assertTrue(set(PUBLIC_FEATURES).issubset(snapshot.columns))
        numeric = [column for column in PUBLIC_FEATURES if column != "country"]
        self.assertTrue(all(pd.api.types.is_numeric_dtype(snapshot[column]) for column in numeric))

    def test_snapshot_fingerprint_survives_csv_dtype_inference(self) -> None:
        snapshot = build_public_customer_snapshots(
            transaction_fixture(),
            ["2020-04-01"],
            lookback_days=365,
            horizon_days=90,
            sql_directory=PROJECT_ROOT / "sql",
        )
        reloaded = pd.read_csv(
            StringIO(snapshot.to_csv(index=False)),
            dtype={"customer_id": "string", "country": "string", "snapshot_date": "string"},
        )
        self.assertEqual(
            public_snapshot_fingerprint(snapshot),
            public_snapshot_fingerprint(reloaded),
        )


if __name__ == "__main__":
    unittest.main()
