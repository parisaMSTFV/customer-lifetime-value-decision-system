"""Transparent translation of predicted value into CRM service tiers."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

TIER_ORDER = ["protect", "grow", "nurture", "low_touch"]


def apply_policy(
    predictions: pd.DataFrame,
    policy_config: dict[str, Any],
) -> pd.DataFrame:
    """Assign relative tiers and conservative investment ceilings."""
    result = predictions.copy()
    descending_rank = result["predicted_clv_180d"].rank(
        method="first",
        ascending=False,
    )
    protect_share = float(policy_config["tier_shares"]["protect"])
    grow_share = float(policy_config["tier_shares"]["grow"])
    nurture_share = float(policy_config["tier_shares"]["nurture"])
    population = len(result)
    protect_count = round(population * protect_share)
    grow_count = round(population * grow_share)
    nurture_count = round(population * nurture_share)

    result["service_tier"] = np.select(
        [
            descending_rank <= protect_count,
            descending_rank <= protect_count + grow_count,
            descending_rank <= protect_count + grow_count + nurture_count,
        ],
        ["protect", "grow", "nurture"],
        default="low_touch",
    )
    uncertainty_ratio = (result["clv_upper_80"] - result["clv_lower_80"]) / result[
        "predicted_clv_180d"
    ].clip(lower=1.0)
    result["high_uncertainty"] = uncertainty_ratio > float(policy_config["uncertainty_ratio"])
    fraction = float(policy_config["investment_fraction"])
    caps = result["service_tier"].map(policy_config["tier_caps"]).astype(float)
    result["investment_ceiling"] = np.minimum(
        result["clv_lower_80"] * fraction,
        caps,
    ).clip(lower=0.0)
    return result


def policy_summary(scored_holdout: pd.DataFrame) -> pd.DataFrame:
    """Summarize predicted and realized holdout value by assigned tier."""
    grouped = (
        scored_holdout.groupby("service_tier", observed=True)
        .agg(
            customers=("customer_id", "count"),
            predicted_value=("predicted_clv_180d", "sum"),
            realized_value=("future_discounted_margin_180d", "sum"),
            investment_ceiling=("investment_ceiling", "sum"),
            high_uncertainty_rate=("high_uncertainty", "mean"),
        )
        .reindex(TIER_ORDER)
        .reset_index()
    )
    grouped["customer_share"] = grouped["customers"] / grouped["customers"].sum()
    grouped["realized_value_share"] = grouped["realized_value"] / grouped["realized_value"].sum()
    return grouped
