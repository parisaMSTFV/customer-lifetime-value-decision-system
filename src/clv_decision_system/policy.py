"""Transparent translation of predicted value into CRM service tiers."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

TIER_ORDER = ["protect", "grow", "nurture", "low_touch"]


def _tier_counts(population: int, shares: dict[str, float]) -> dict[str, int]:
    """Allocate every row using largest remainders across all configured shares."""
    exact = {tier: population * float(shares[tier]) for tier in TIER_ORDER}
    counts = {tier: int(np.floor(exact[tier])) for tier in TIER_ORDER}
    remainder = population - sum(counts.values())
    priority = sorted(
        TIER_ORDER,
        key=lambda tier: (-(exact[tier] - counts[tier]), TIER_ORDER.index(tier)),
    )
    for tier in priority[:remainder]:
        counts[tier] += 1
    return counts


def apply_policy(
    predictions: pd.DataFrame,
    policy_config: dict[str, Any],
) -> pd.DataFrame:
    """Assign relative tiers and conservative investment ceilings."""
    result = predictions.copy()
    population = len(result)
    if population == 0:
        raise ValueError("Policy requires at least one prediction")
    if not np.isfinite(result["predicted_clv_180d"].to_numpy()).all():
        raise ValueError("Policy predictions must be finite")
    counts = _tier_counts(population, policy_config["tier_shares"])
    ordered_index = result.sort_values(["predicted_clv_180d"], ascending=False, kind="stable").index
    assignments: list[str] = []
    for tier in TIER_ORDER:
        assignments.extend([tier] * counts[tier])
    result.loc[ordered_index, "service_tier"] = assignments
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
