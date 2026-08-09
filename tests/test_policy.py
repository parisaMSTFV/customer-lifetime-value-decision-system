"""Tests for tier assignment and policy guardrails."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from clv_decision_system.policy import apply_policy, policy_summary  # noqa: E402, I001

POLICY = {
    "tier_shares": {"protect": 0.10, "grow": 0.20, "nurture": 0.40, "low_touch": 0.30},
    "investment_fraction": 0.08,
    "tier_caps": {"protect": 24.0, "grow": 14.0, "nurture": 7.0, "low_touch": 2.0},
    "uncertainty_ratio": 1.25,
}


class PolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        values = np.arange(1, 101, dtype=float)
        self.predictions = pd.DataFrame(
            {
                "predicted_clv_180d": values,
                "active_probability_180d": np.linspace(0.1, 0.9, 100),
                "clv_lower_80": values * 0.6,
                "clv_upper_80": values * 1.4,
            }
        )

    def test_tier_counts_follow_configured_capacity(self) -> None:
        result = apply_policy(self.predictions, POLICY)
        self.assertEqual((result["service_tier"] == "protect").sum(), 10)
        self.assertEqual((result["service_tier"] == "grow").sum(), 20)
        self.assertEqual((result["service_tier"] == "nurture").sum(), 40)
        self.assertEqual((result["service_tier"] == "low_touch").sum(), 30)

    def test_investment_ceiling_never_exceeds_tier_cap(self) -> None:
        result = apply_policy(self.predictions, POLICY)
        caps = result["service_tier"].map(POLICY["tier_caps"])
        self.assertTrue((result["investment_ceiling"] <= caps).all())

    def test_policy_summary_shares_sum_to_one(self) -> None:
        decisions = apply_policy(self.predictions, POLICY)
        scored = decisions.assign(
            customer_id=[f"C{value:03d}" for value in range(100)],
            future_discounted_margin_180d=np.arange(1, 101, dtype=float),
        )
        summary = policy_summary(scored)
        self.assertAlmostEqual(summary["customer_share"].sum(), 1.0)
        self.assertAlmostEqual(summary["realized_value_share"].sum(), 1.0)


if __name__ == "__main__":
    unittest.main()
