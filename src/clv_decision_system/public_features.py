"""Leakage-safe public customer snapshots built with executable DuckDB SQL."""

from __future__ import annotations

import hashlib
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

PUBLIC_TARGET_COLUMN = "future_net_revenue_180d"
PUBLIC_ACTIVE_COLUMN = "future_active_180d"
PUBLIC_CATEGORICAL_FEATURES = ["country"]
PUBLIC_NUMERIC_FEATURES = [
    "observed_tenure_days",
    "recency_days",
    "orders_30d",
    "orders_90d",
    "orders_180d",
    "orders_365d",
    "net_revenue_90d",
    "net_revenue_previous_90d",
    "net_revenue_180d",
    "net_revenue_365d",
    "average_order_value_365d",
    "return_value_ratio_365d",
    "product_diversity_365d",
    "active_months_365d",
    "revenue_momentum_90d",
    "recent_order_share",
]
PUBLIC_FEATURES = PUBLIC_CATEGORICAL_FEATURES + PUBLIC_NUMERIC_FEATURES


def public_snapshot_fingerprint(frame: pd.DataFrame) -> str:
    """Hash a stable text representation independent of inferred CSV dtypes."""
    ordered = frame.sort_values(["snapshot_date", "customer_id"]).reset_index(drop=True)
    content = ordered.to_csv(
        index=False,
        date_format="%Y-%m-%d",
        float_format="%.10g",
        lineterminator="\n",
    )
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


def _sql(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip().rstrip(";")


def validate_public_snapshots(frame: pd.DataFrame, expected_dates: list[str]) -> None:
    """Fail on broken keys, dates, values, or feature contracts."""
    required = {
        "customer_id",
        "snapshot_date",
        PUBLIC_TARGET_COLUMN,
        PUBLIC_ACTIVE_COLUMN,
        *PUBLIC_FEATURES,
    }
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"Public snapshots are missing columns: {sorted(missing)}")
    if frame.duplicated(["customer_id", "snapshot_date"]).any():
        raise ValueError("Duplicate public customer-snapshot rows detected")
    if frame[list(required)].isna().any().any():
        raise ValueError("Public snapshots contain missing model values")
    observed = sorted(pd.to_datetime(frame["snapshot_date"]).dt.strftime("%Y-%m-%d").unique())
    if observed != sorted(expected_dates):
        raise ValueError(f"Public snapshot dates differ from configuration: {observed}")
    if not frame[PUBLIC_ACTIVE_COLUMN].isin([0, 1]).all():
        raise ValueError("Future public activity must be binary")
    numeric = frame.select_dtypes(include="number")
    if not np.isfinite(numeric.to_numpy()).all():
        raise ValueError("Public snapshot values must be finite")


def build_public_customer_snapshots(
    transactions: pd.DataFrame,
    snapshot_dates: list[str],
    lookback_days: int,
    horizon_days: int,
    sql_directory: str | Path,
) -> pd.DataFrame:
    """Execute the public transaction contract, feature SQL, and future-label SQL."""
    if transactions.empty:
        raise ValueError("Public transactions must not be empty")
    observed_start = pd.to_datetime(transactions["invoice_date"]).min()
    incomplete = {
        snapshot_date: int((pd.Timestamp(snapshot_date) - observed_start.normalize()).days)
        for snapshot_date in snapshot_dates
        if pd.Timestamp(snapshot_date) - observed_start < pd.Timedelta(days=lookback_days)
    }
    if incomplete:
        raise ValueError(
            "Public snapshots do not have a complete lookback window: "
            f"{incomplete}; required={lookback_days}"
        )

    sql_path = Path(sql_directory)
    contract_sql = (sql_path / "public_transaction_contract.sql").read_text(encoding="utf-8")
    feature_sql = _sql(sql_path / "public_customer_features.sql")
    label_sql = _sql(sql_path / "public_customer_label.sql")
    connection = duckdb.connect(":memory:")
    try:
        connection.register("transactions_source", transactions)
        connection.execute(contract_sql)
        snapshots: list[pd.DataFrame] = []
        for snapshot_date in snapshot_dates:
            connection.execute(
                """
                CREATE OR REPLACE TEMP TABLE snapshot_parameters AS
                SELECT CAST(? AS TIMESTAMP) AS snapshot_date,
                       CAST(? AS INTEGER) AS lookback_days,
                       CAST(? AS INTEGER) AS horizon_days
                """,
                [snapshot_date, lookback_days, horizon_days],
            )
            connection.execute(
                f"CREATE OR REPLACE TEMP VIEW public_customer_features AS {feature_sql}"
            )
            connection.execute(f"CREATE OR REPLACE TEMP VIEW public_customer_labels AS {label_sql}")
            snapshot = connection.execute(
                """
                SELECT features.*, labels.future_net_revenue_180d, labels.future_active_180d
                FROM public_customer_features AS features
                INNER JOIN public_customer_labels AS labels
                    USING (customer_id, snapshot_date)
                ORDER BY customer_id
                """
            ).df()
            snapshots.append(snapshot)
    finally:
        connection.close()
    result = pd.concat(snapshots, ignore_index=True)
    result["snapshot_date"] = pd.to_datetime(result["snapshot_date"]).dt.strftime("%Y-%m-%d")
    validate_public_snapshots(result, snapshot_dates)
    return result.sort_values(["snapshot_date", "customer_id"]).reset_index(drop=True)


def build_public_customer_snapshots_pandas(
    transactions: pd.DataFrame,
    snapshot_dates: list[str],
    lookback_days: int,
    horizon_days: int,
) -> pd.DataFrame:
    """Small reference implementation used only for SQL parity tests."""
    snapshots: list[pd.DataFrame] = []
    source = transactions.copy()
    source["invoice_date"] = pd.to_datetime(source["invoice_date"])
    source["invoice_day"] = source["invoice_date"].dt.normalize()
    for snapshot_text in snapshot_dates:
        snapshot = pd.Timestamp(snapshot_text)
        past = source[source["invoice_date"] < snapshot].copy()
        positive_past = past[(~past["is_cancellation"]) & (past["signed_revenue"] > 0)]
        first_purchase = positive_past.groupby("customer_id")["invoice_date"].min()
        latest_country = (
            past.sort_values("invoice_date", kind="stable")
            .groupby("customer_id", as_index=True)["country"]
            .last()
        )
        eligible = first_purchase.index
        history = past[past["invoice_date"] >= snapshot - pd.Timedelta(days=lookback_days)].copy()
        history["age_days"] = (snapshot.normalize() - history["invoice_day"]).dt.days
        future = source[
            (source["invoice_date"] >= snapshot)
            & (source["invoice_date"] < snapshot + pd.Timedelta(days=horizon_days))
        ]
        rows: list[dict[str, object]] = []
        for customer_id in eligible:
            customer_history = history[history["customer_id"] == customer_id]
            positive = customer_history[
                (~customer_history["is_cancellation"]) & (customer_history["signed_revenue"] > 0)
            ]

            def orders(days: int, positive_frame: pd.DataFrame = positive) -> int:
                return int(
                    positive_frame.loc[positive_frame["age_days"] <= days, "invoice_id"].nunique()
                )

            def net_revenue(
                start_exclusive: int,
                end_inclusive: int,
                history_frame: pd.DataFrame = customer_history,
            ) -> float:
                window = history_frame[
                    (history_frame["age_days"] > start_exclusive)
                    & (history_frame["age_days"] <= end_inclusive)
                ]
                return float(window["signed_revenue"].sum())

            revenue_90 = net_revenue(-1, 90)
            previous_90 = net_revenue(90, 180)
            revenue_180 = net_revenue(-1, 180)
            revenue_365 = net_revenue(-1, 365)
            positive_365 = positive[positive["age_days"] <= 365]
            history_365 = customer_history[customer_history["age_days"] <= 365]
            order_count_365 = orders(365)
            gross = float(positive_365["signed_revenue"].sum())
            returned = -float(
                history_365.loc[history_365["is_cancellation"], "signed_revenue"].sum()
            )
            customer_future = future[future["customer_id"] == customer_id]
            future_value = float(customer_future["signed_revenue"].sum())
            future_activity = not customer_future.empty
            observed_tenure_days = int(
                (snapshot.normalize() - first_purchase.loc[customer_id].normalize()).days
            )
            recency_days = (
                int(positive["age_days"].min()) if not positive.empty else lookback_days + 1
            )
            rows.append(
                {
                    "customer_id": customer_id,
                    "snapshot_date": snapshot_text,
                    "country": latest_country.loc[customer_id],
                    "observed_tenure_days": observed_tenure_days,
                    "recency_days": recency_days,
                    "orders_30d": orders(30),
                    "orders_90d": orders(90),
                    "orders_180d": orders(180),
                    "orders_365d": order_count_365,
                    "net_revenue_90d": revenue_90,
                    "net_revenue_previous_90d": previous_90,
                    "net_revenue_180d": revenue_180,
                    "net_revenue_365d": revenue_365,
                    "average_order_value_365d": (
                        revenue_365 / order_count_365 if order_count_365 else 0.0
                    ),
                    "return_value_ratio_365d": returned / gross if gross else 0.0,
                    "product_diversity_365d": int(positive_365["stock_code"].nunique()),
                    "active_months_365d": int(
                        positive_365["invoice_date"].dt.to_period("M").nunique()
                    ),
                    "revenue_momentum_90d": (revenue_90 - previous_90)
                    / (abs(revenue_90) + abs(previous_90) + 1.0),
                    "recent_order_share": orders(90) / order_count_365 if order_count_365 else 0.0,
                    PUBLIC_TARGET_COLUMN: future_value,
                    PUBLIC_ACTIVE_COLUMN: int(future_activity),
                }
            )
        snapshots.append(pd.DataFrame(rows))
    result = pd.concat(snapshots, ignore_index=True)
    validate_public_snapshots(result, snapshot_dates)
    return result.sort_values(["snapshot_date", "customer_id"]).reset_index(drop=True)
