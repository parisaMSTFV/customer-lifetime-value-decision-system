"""Tests for public two-part modeling and uncertainty calibration."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from clv_decision_system.public_features import (  # noqa: E402, I001
    PUBLIC_ACTIVE_COLUMN,
    PUBLIC_NUMERIC_FEATURES,
    PUBLIC_TARGET_COLUMN,
)
from clv_decision_system.public_modeling import (  # noqa: E402, I001
    calibrate_public_intervals,
    fit_public_model,
    predict_public,
    public_revenue_baseline,
)


def public_training_frame(rows: int = 180) -> pd.DataFrame:
    rng = np.random.default_rng(33)
    frame = pd.DataFrame(index=range(rows))
    frame["country"] = rng.choice(["UK", "France", "Germany"], rows)
    for column in PUBLIC_NUMERIC_FEATURES:
        frame[column] = rng.uniform(0.0, 20.0, rows)
    frame["recency_days"] = rng.uniform(1.0, 300.0, rows)
    target = np.where(
        np.arange(rows) % 4 == 0,
        0.0,
        15.0 + frame["net_revenue_180d"] * 3.0,
    )
    frame[PUBLIC_TARGET_COLUMN] = target
    frame[PUBLIC_ACTIVE_COLUMN] = (target > 0).astype(int)
    return frame


class PublicModelingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.frame = public_training_frame()
        cls.bundle = fit_public_model(
            cls.frame,
            {"max_leaf_nodes": 9, "learning_rate": 0.07, "min_samples_leaf": 15},
            seed=33,
        )

    def test_public_predictions_are_non_negative_and_ordered(self) -> None:
        result = predict_public(self.bundle, self.frame.head(30))
        self.assertTrue((result["predicted_revenue_180d"] >= 0).all())
        self.assertTrue((result["revenue_lower_80"] <= result["predicted_revenue_180d"]).all())
        self.assertTrue((result["predicted_revenue_180d"] <= result["revenue_upper_80"]).all())

    def test_public_conformal_calibration_reaches_snapshot_target(self) -> None:
        calibration_frame = self.frame.iloc[:80].copy()
        raw = predict_public(self.bundle, calibration_frame)
        calibration_frame[PUBLIC_TARGET_COLUMN] = raw[
            "revenue_upper_80_raw"
        ].to_numpy() + np.linspace(0.0, 20.0, len(calibration_frame))
        calibration = calibrate_public_intervals(
            self.bundle, calibration_frame, target_coverage=0.80
        )
        calibrated = predict_public(self.bundle, calibration_frame, calibration)
        covered = (calibration_frame[PUBLIC_TARGET_COLUMN] >= calibrated["revenue_lower_80"]) & (
            calibration_frame[PUBLIC_TARGET_COLUMN] <= calibrated["revenue_upper_80"]
        )
        self.assertGreater(calibration.correction, 0.0)
        self.assertGreaterEqual(covered.mean(), 0.80)

    def test_public_conformal_calibration_does_not_shrink_overcoverage(self) -> None:
        calibration_frame = self.frame.iloc[:80].copy()
        raw = predict_public(self.bundle, calibration_frame)
        calibration_frame[PUBLIC_TARGET_COLUMN] = (
            raw["revenue_lower_80_raw"].to_numpy() + raw["revenue_upper_80_raw"].to_numpy()
        ) / 2
        calibration = calibrate_public_intervals(
            self.bundle, calibration_frame, target_coverage=0.80
        )
        self.assertEqual(calibration.correction, 0.0)

    def test_public_baseline_penalizes_recency(self) -> None:
        frame = pd.DataFrame(
            {
                "recency_days": [1.0, 300.0],
                "net_revenue_90d": [50.0, 50.0],
                "net_revenue_previous_90d": [50.0, 50.0],
                "net_revenue_180d": [100.0, 100.0],
            }
        )
        baseline = public_revenue_baseline(frame)
        self.assertGreater(baseline[0], baseline[1])


if __name__ == "__main__":
    unittest.main()
