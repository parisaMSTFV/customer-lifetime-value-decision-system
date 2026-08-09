"""Deterministic synthetic ecommerce data generation."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class SegmentSpec:
    """Latent behavior used only by the synthetic generator."""

    monthly_rate: float
    average_order_value: float
    margin_rate: float
    trend: float
    seasonality: float
    return_rate: float


SEGMENTS: dict[str, SegmentSpec] = {
    "loyal": SegmentSpec(1.35, 88.0, 0.32, 0.004, 0.10, 0.04),
    "growth": SegmentSpec(0.75, 72.0, 0.29, 0.024, 0.08, 0.06),
    "seasonal": SegmentSpec(0.62, 103.0, 0.30, 0.002, 0.42, 0.05),
    "fading": SegmentSpec(0.95, 79.0, 0.27, -0.027, 0.08, 0.10),
    "occasional": SegmentSpec(0.27, 61.0, 0.25, -0.002, 0.06, 0.08),
}


def generate_customers(n_customers: int, seed: int) -> pd.DataFrame:
    """Generate a synthetic customer table without protected attributes."""
    rng = np.random.default_rng(seed)
    customer_ids = [f"C{index:05d}" for index in range(1, n_customers + 1)]
    segment_names = np.array(list(SEGMENTS))
    latent_segment = rng.choice(
        segment_names,
        size=n_customers,
        p=[0.18, 0.23, 0.16, 0.19, 0.24],
    )
    acquisition_start = np.datetime64("2020-01-01")
    acquisition_days = rng.integers(0, 730, size=n_customers)
    acquisition_date = acquisition_start + acquisition_days.astype("timedelta64[D]")
    customer_effect = rng.lognormal(mean=0.0, sigma=0.28, size=n_customers)

    customers = pd.DataFrame(
        {
            "customer_id": customer_ids,
            "acquisition_date": pd.to_datetime(acquisition_date).date,
            "acquisition_channel": rng.choice(
                ["organic", "paid_search", "affiliate", "referral"],
                size=n_customers,
                p=[0.36, 0.29, 0.18, 0.17],
            ),
            "region": rng.choice(
                ["north", "central", "south", "west"],
                size=n_customers,
                p=[0.24, 0.35, 0.23, 0.18],
            ),
            "_latent_segment": latent_segment,
            "_customer_effect": customer_effect,
        }
    )
    return customers


def _monthly_rate(
    spec: SegmentSpec,
    month_index: int,
    month: pd.Timestamp,
    customer_effect: float,
) -> float:
    elapsed_years = month_index / 12
    trend_multiplier = np.exp(spec.trend * month_index)
    seasonal_peak = 1 + spec.seasonality * np.cos(2 * np.pi * (month.month - 11) / 12)
    market_cycle = 1 + 0.07 * np.sin(2 * np.pi * elapsed_years / 1.8)
    rate = spec.monthly_rate * trend_multiplier * seasonal_peak * market_cycle
    return max(0.01, rate * customer_effect)


def generate_orders(
    customers: pd.DataFrame,
    start_date: str,
    end_date: str,
    seed: int,
) -> pd.DataFrame:
    """Generate order-level behavior with lifecycle, trend, and seasonal signals."""
    rng = np.random.default_rng(seed + 1)
    months = pd.date_range(start_date, end_date, freq="MS")
    categories = np.array(["home", "beauty", "electronics", "grocery", "fashion"])
    channels = np.array(["app", "web", "assisted"])
    records: list[dict[str, object]] = []
    order_number = 1

    for customer in customers.to_dict(orient="records"):
        spec = SEGMENTS[str(customer["_latent_segment"])]
        acquisition_date = pd.Timestamp(customer["acquisition_date"])
        for month_index, month in enumerate(months):
            if month < acquisition_date.to_period("M").to_timestamp():
                continue
            rate = _monthly_rate(
                spec,
                month_index,
                month,
                float(customer["_customer_effect"]),
            )
            order_count = min(int(rng.poisson(rate)), 6)
            for _ in range(order_count):
                last_day = min((month + pd.offsets.MonthEnd(0)).day, 28)
                order_date = month + pd.Timedelta(days=int(rng.integers(0, last_day)))
                if order_date > pd.Timestamp(end_date):
                    continue
                discount_ratio = float(np.clip(rng.beta(1.8, 9.0), 0.0, 0.45))
                gross_revenue = float(
                    rng.lognormal(mean=np.log(spec.average_order_value), sigma=0.34)
                )
                net_revenue = gross_revenue * (1 - discount_ratio)
                returned = bool(rng.random() < spec.return_rate)
                category = str(
                    rng.choice(
                        categories,
                        p=[0.21, 0.18, 0.18, 0.24, 0.19],
                    )
                )
                margin_noise = rng.normal(0.0, 0.025)
                margin_rate = float(np.clip(spec.margin_rate + margin_noise, 0.14, 0.42))
                fulfillment_cost = 4.0 + 0.025 * net_revenue
                return_cost = 0.42 * net_revenue + 3.5 if returned else 0.0
                contribution_margin = max(
                    0.5,
                    net_revenue * margin_rate - fulfillment_cost - return_cost,
                )
                records.append(
                    {
                        "order_id": f"O{order_number:07d}",
                        "customer_id": customer["customer_id"],
                        "order_date": order_date.date(),
                        "category": category,
                        "order_channel": str(rng.choice(channels, p=[0.58, 0.38, 0.04])),
                        "net_revenue": round(net_revenue, 2),
                        "contribution_margin": round(contribution_margin, 2),
                        "discount_ratio": round(discount_ratio, 4),
                        "returned": int(returned),
                    }
                )
                order_number += 1

    orders = pd.DataFrame.from_records(records)
    return orders.sort_values(["order_date", "order_id"]).reset_index(drop=True)


def public_customer_columns(customers: pd.DataFrame) -> pd.DataFrame:
    """Remove latent generator fields before data is persisted."""
    return customers.drop(columns=["_latent_segment", "_customer_effect"])
