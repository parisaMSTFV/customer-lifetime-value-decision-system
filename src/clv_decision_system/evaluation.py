"""Evaluation metrics for value prediction, ranking, and activity probability."""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.metrics import average_precision_score, brier_score_loss, mean_absolute_error

from .modeling import ModelBundle, predict, wape


def top_fraction_capture(actual: np.ndarray, score: np.ndarray, fraction: float) -> float:
    """Share of total realized value captured in the highest-scored fraction."""
    count = max(1, int(np.ceil(len(actual) * fraction)))
    selected = np.argsort(-score)[:count]
    denominator = float(actual.sum())
    return float(actual[selected].sum() / denominator) if denominator else 0.0


def regression_metrics(
    actual: np.ndarray,
    predicted: np.ndarray,
    lower: np.ndarray | None = None,
    upper: np.ndarray | None = None,
) -> dict[str, float]:
    """Calculate scale, ranking, and optional interval metrics."""
    rank_correlation = spearmanr(actual, predicted).statistic
    metrics = {
        "mae": float(mean_absolute_error(actual, predicted)),
        "wape": wape(actual, predicted),
        "rmse": float(np.sqrt(np.mean((actual - predicted) ** 2))),
        "spearman": float(0.0 if np.isnan(rank_correlation) else rank_correlation),
        "top_10_value_capture": top_fraction_capture(actual, predicted, 0.10),
        "top_20_value_capture": top_fraction_capture(actual, predicted, 0.20),
    }
    if lower is not None and upper is not None:
        metrics["interval_80_coverage"] = float(np.mean((actual >= lower) & (actual <= upper)))
        metrics["interval_mean_width"] = float(np.mean(upper - lower))
    return metrics


def full_evaluation(
    frame: pd.DataFrame,
    predictions: pd.DataFrame,
    baseline: np.ndarray,
) -> dict[str, dict[str, float]]:
    """Compare the final model with the fixed business baseline."""
    actual = frame["future_discounted_margin_180d"].to_numpy()
    active = frame["future_active_180d"].to_numpy()
    model_metrics = regression_metrics(
        actual,
        predictions["predicted_clv_180d"].to_numpy(),
        predictions["clv_lower_80"].to_numpy(),
        predictions["clv_upper_80"].to_numpy(),
    )
    raw_interval_metrics = regression_metrics(
        actual,
        predictions["predicted_clv_180d"].to_numpy(),
        predictions["clv_lower_80_raw"].to_numpy(),
        predictions["clv_upper_80_raw"].to_numpy(),
    )
    model_metrics["interval_80_raw_coverage"] = raw_interval_metrics["interval_80_coverage"]
    model_metrics["interval_raw_mean_width"] = raw_interval_metrics["interval_mean_width"]
    model_metrics.update(
        {
            "activity_average_precision": float(
                average_precision_score(active, predictions["active_probability_180d"])
            ),
            "activity_brier_score": float(
                brier_score_loss(active, predictions["active_probability_180d"])
            ),
        }
    )
    return {
        "model": model_metrics,
        "baseline": regression_metrics(actual, baseline),
    }


def interval_diagnostics(
    scored: pd.DataFrame,
    group_column: str,
) -> pd.DataFrame:
    """Report raw and calibrated interval performance by an operating group."""
    required = {
        group_column,
        "future_discounted_margin_180d",
        "clv_lower_80_raw",
        "clv_upper_80_raw",
        "clv_lower_80",
        "clv_upper_80",
    }
    missing = required.difference(scored.columns)
    if missing:
        raise ValueError(f"Missing interval diagnostic columns: {sorted(missing)}")

    frame = scored.copy()
    actual = frame["future_discounted_margin_180d"]
    frame["raw_covered"] = (actual >= frame["clv_lower_80_raw"]) & (
        actual <= frame["clv_upper_80_raw"]
    )
    frame["calibrated_covered"] = (actual >= frame["clv_lower_80"]) & (
        actual <= frame["clv_upper_80"]
    )
    frame["raw_width"] = frame["clv_upper_80_raw"] - frame["clv_lower_80_raw"]
    frame["calibrated_width"] = frame["clv_upper_80"] - frame["clv_lower_80"]
    return (
        frame.groupby(group_column, observed=True)
        .agg(
            customers=("customer_id", "count"),
            raw_coverage=("raw_covered", "mean"),
            calibrated_coverage=("calibrated_covered", "mean"),
            raw_mean_width=("raw_width", "mean"),
            calibrated_mean_width=("calibrated_width", "mean"),
        )
        .reset_index()
    )


def permutation_wape_importance(
    bundle: ModelBundle,
    frame: pd.DataFrame,
    features: list[str],
    seed: int,
) -> pd.DataFrame:
    """Estimate feature importance as holdout WAPE deterioration after permutation."""
    rng = np.random.default_rng(seed)
    actual = frame["future_discounted_margin_180d"].to_numpy()
    baseline_wape = wape(actual, predict(bundle, frame)["predicted_clv_180d"].to_numpy())
    rows: list[dict[str, float | str]] = []
    for feature in features:
        shuffled = frame.copy()
        shuffled[feature] = rng.permutation(shuffled[feature].to_numpy())
        shuffled_wape = wape(
            actual,
            predict(bundle, shuffled)["predicted_clv_180d"].to_numpy(),
        )
        rows.append(
            {
                "feature": feature,
                "wape_increase": max(0.0, shuffled_wape - baseline_wape),
            }
        )
    return pd.DataFrame(rows).sort_values("wape_increase", ascending=False).reset_index(drop=True)
