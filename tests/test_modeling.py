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
    regression_metrics,
    top_fraction_capture,
)
from clv_decision_system.modeling import (  # noqa: E402, I001
    ACTIVE_COLUMN,
    CATEGORICAL_FEATURES,
    NUMERIC_FEATURES,
    TARGET_COLUMN,
    baseline_prediction,
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
        self.assertTrue((result["clv_lower_80"] <= result["predicted_clv_180d"]).all())
        self.assertTrue((result["predicted_clv_180d"] <= result["clv_upper_80"]).all())

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


if __name__ == "__main__":
    unittest.main()
