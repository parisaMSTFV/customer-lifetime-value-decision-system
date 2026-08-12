"""Tests for modeling and metric contracts."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from clv_decision_system.evaluation import (  # noqa: E402, I001
    interval_diagnostics,
    regression_metrics,
    top_fraction_capture,
)
from clv_decision_system.modeling import (  # noqa: E402, I001
    ACTIVE_COLUMN,
    CATEGORICAL_FEATURES,
    NUMERIC_FEATURES,
    TARGET_COLUMN,
    baseline_prediction,
    calibrate_intervals,
    fit_final_model,
    predict,
    wape,
)


def make_training_frame(rows: int = 120) -> pd.DataFrame:
    rng = np.random.default_rng(19)
    frame = pd.DataFrame(index=range(rows))
    frame["acquisition_channel"] = rng.choice(["organic", "referral"], rows)
    frame["region"] = rng.choice(["north", "south"], rows)
    for column in NUMERIC_FEATURES:
        frame[column] = rng.uniform(0, 10, rows)
    target = np.where(np.arange(rows) % 3 == 0, 0.0, 20 + frame["margin_180d"] * 4)
    frame[TARGET_COLUMN] = target
    frame[ACTIVE_COLUMN] = (target > 0).astype(int)
    return frame


class ModelingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.frame = make_training_frame()
        cls.bundle = fit_final_model(
            cls.frame,
            {"max_leaf_nodes": 9, "learning_rate": 0.08, "min_samples_leaf": 10},
            seed=19,
        )

    def test_all_declared_features_exist(self) -> None:
        self.assertTrue(set(CATEGORICAL_FEATURES + NUMERIC_FEATURES).issubset(self.frame))

    def test_predictions_are_non_negative_and_intervals_are_ordered(self) -> None:
        result = predict(self.bundle, self.frame.head(20))
        self.assertTrue((result["predicted_clv_180d"] >= 0).all())
        self.assertTrue((result["clv_lower_80_raw"] <= result["predicted_clv_180d"]).all())
        self.assertTrue((result["predicted_clv_180d"] <= result["clv_upper_80_raw"]).all())
        self.assertTrue((result["clv_lower_80"] <= result["predicted_clv_180d"]).all())
        self.assertTrue((result["predicted_clv_180d"] <= result["clv_upper_80"]).all())

    def test_interval_calibration_reaches_target_on_calibration_snapshot(self) -> None:
        calibration_frame = self.frame.iloc[:60].copy()
        raw = predict(self.bundle, calibration_frame)
        calibration_frame[TARGET_COLUMN] = raw["clv_upper_80_raw"].to_numpy() + np.linspace(
            0.0, 25.0, len(calibration_frame)
        )
        calibration = calibrate_intervals(self.bundle, calibration_frame, target_coverage=0.80)
        calibrated = predict(self.bundle, calibration_frame, calibration)
        covered = (calibration_frame[TARGET_COLUMN] >= calibrated["clv_lower_80"]) & (
            calibration_frame[TARGET_COLUMN] <= calibrated["clv_upper_80"]
        )
        self.assertGreater(calibration.correction, 0.0)
        self.assertGreaterEqual(covered.mean(), 0.80)
        self.assertTrue((calibrated["clv_upper_80"] >= calibrated["clv_upper_80_raw"]).all())

    def test_baseline_penalizes_long_recency(self) -> None:
        frame = pd.DataFrame(
            {
                "margin_180d": [100.0, 100.0],
                "margin_90d": [50.0, 50.0],
                "margin_previous_90d": [50.0, 50.0],
                "recency_days": [1, 300],
            }
        )
        result = baseline_prediction(frame)
        self.assertGreater(result[0], result[1])

    def test_wape_is_zero_for_exact_prediction(self) -> None:
        actual = np.array([0.0, 10.0, 20.0])
        self.assertEqual(wape(actual, actual), 0.0)

    def test_regression_metrics_include_ranking_and_scale(self) -> None:
        actual = np.array([0.0, 10.0, 30.0, 50.0])
        predicted = np.array([1.0, 9.0, 29.0, 52.0])
        metrics = regression_metrics(actual, predicted)
        self.assertIn("wape", metrics)
        self.assertGreater(metrics["spearman"], 0.9)

    def test_top_fraction_capture_uses_highest_scores(self) -> None:
        actual = np.array([1.0, 2.0, 7.0, 10.0])
        score = np.array([0.0, 1.0, 2.0, 3.0])
        self.assertEqual(top_fraction_capture(actual, score, 0.25), 0.5)

    def test_interval_diagnostics_reports_raw_and_calibrated_coverage(self) -> None:
        scored = pd.DataFrame(
            {
                "customer_id": ["C1", "C2"],
                "service_tier": ["protect", "protect"],
                "future_discounted_margin_180d": [10.0, 30.0],
                "clv_lower_80_raw": [8.0, 8.0],
                "clv_upper_80_raw": [12.0, 12.0],
                "clv_lower_80": [5.0, 5.0],
                "clv_upper_80": [35.0, 35.0],
            }
        )
        result = interval_diagnostics(scored, "service_tier").iloc[0]
        self.assertEqual(result["raw_coverage"], 0.5)
        self.assertEqual(result["calibrated_coverage"], 1.0)
        self.assertGreater(result["calibrated_mean_width"], result["raw_mean_width"])


if __name__ == "__main__":
    unittest.main()
