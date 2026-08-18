"""Leakage-safe temporal snapshot construction using executable SQL."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

TARGET_COLUMN = "future_discounted_margin_180d"


def _prepare_for_sql(frame: pd.DataFrame) -> pd.DataFrame:
    prepared = frame.copy()
    for column in prepared.columns:
        if "date" in column:
            prepared[column] = pd.to_datetime(prepared[column]).dt.strftime("%Y-%m-%d")
    return prepared


def build_customer_snapshots(
    customers: pd.DataFrame,
    orders: pd.DataFrame,
    snapshot_dates: list[str],
    lookback_days: int,
    horizon_days: int,
    annual_discount_rate: float,
    sql_directory: str | Path,
) -> pd.DataFrame:
    """Build feature and outcome snapshots with strict as-of-date filters."""
    sql_path = Path(sql_directory)
    feature_sql = (sql_path / "customer_value_snapshot.sql").read_text(encoding="utf-8")
    label_sql = (sql_path / "customer_value_label.sql").read_text(encoding="utf-8")

    connection = sqlite3.connect(":memory:")
    try:
        _prepare_for_sql(customers).to_sql("customers", connection, index=False)
        _prepare_for_sql(orders).to_sql("orders", connection, index=False)
        connection.execute(
            "CREATE INDEX idx_orders_customer_date ON orders(customer_id, order_date)"
        )

        snapshots: list[pd.DataFrame] = []
        for snapshot_date in snapshot_dates:
            feature_parameters = {
                "snapshot_date": snapshot_date,
                "lookback_days": lookback_days,
            }
            label_parameters = {
                "snapshot_date": snapshot_date,
                "horizon_days": horizon_days,
                "annual_discount_rate": annual_discount_rate,
            }
            features = pd.read_sql_query(feature_sql, connection, params=feature_parameters)
            labels = pd.read_sql_query(label_sql, connection, params=label_parameters)
            snapshot = features.merge(
                labels,
                on=["customer_id", "snapshot_date"],
                validate="one_to_one",
            )
            snapshot["future_active_180d"] = (snapshot["future_orders_180d"] > 0).astype(int)
            snapshots.append(snapshot)
    finally:
        connection.close()

    result = pd.concat(snapshots, ignore_index=True)
    validate_snapshots(result, expected_dates=snapshot_dates)
    return result.sort_values(["snapshot_date", "customer_id"]).reset_index(drop=True)


def validate_snapshots(frame: pd.DataFrame, expected_dates: list[str]) -> None:
    """Fail fast on structural errors that could invalidate evaluation."""
    if frame.duplicated(["customer_id", "snapshot_date"]).any():
        raise ValueError("Duplicate customer-snapshot rows detected")
    if frame.isna().any().any():
        missing = frame.columns[frame.isna().any()].tolist()
        raise ValueError(f"Missing values detected in snapshot columns: {missing}")
    observed_dates = sorted(frame["snapshot_date"].astype(str).unique().tolist())
    if observed_dates != sorted(expected_dates):
        raise ValueError(f"Snapshot dates differ from configuration: {observed_dates}")
    numeric = frame.select_dtypes(include="number")
    if not np.isfinite(numeric.to_numpy()).all():
        raise ValueError("Synthetic snapshot values must be finite")
