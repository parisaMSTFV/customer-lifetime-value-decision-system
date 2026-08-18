"""Out-of-simulation value validation on licensed public retail transactions."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pandas as pd
from sklearn.metrics import average_precision_score, brier_score_loss

from .config import load_public_validation_config
from .evaluation import paired_bootstrap_comparison, regression_metrics
from .pipeline import _split_snapshots
from .public_features import PUBLIC_TARGET_COLUMN, public_snapshot_fingerprint
from .public_modeling import (
    calibrate_public_intervals,
    fit_public_model,
    predict_public,
    public_permutation_importance,
    public_revenue_baseline,
    select_public_parameters,
)
from .public_reporting import create_public_reports


def _interval_by_decile(scored: pd.DataFrame) -> pd.DataFrame:
    frame = scored.copy()
    actual = frame[PUBLIC_TARGET_COLUMN]
    frame["raw_covered"] = (actual >= frame["revenue_lower_80_raw"]) & (
        actual <= frame["revenue_upper_80_raw"]
    )
    frame["calibrated_covered"] = (actual >= frame["revenue_lower_80"]) & (
        actual <= frame["revenue_upper_80"]
    )
    frame["raw_width"] = frame["revenue_upper_80_raw"] - frame["revenue_lower_80_raw"]
    frame["calibrated_width"] = frame["revenue_upper_80"] - frame["revenue_lower_80"]
    return (
        frame.groupby("predicted_value_decile", observed=True)
        .agg(
            customers=("customer_id", "count"),
            raw_coverage=("raw_covered", "mean"),
            calibrated_coverage=("calibrated_covered", "mean"),
            raw_mean_width=("raw_width", "mean"),
            calibrated_mean_width=("calibrated_width", "mean"),
        )
        .reset_index()
    )


def _decile_summary(scored: pd.DataFrame) -> pd.DataFrame:
    total = scored[PUBLIC_TARGET_COLUMN].sum()
    result = (
        scored.groupby("predicted_value_decile", observed=True)
        .agg(
            customers=("customer_id", "count"),
            average_predicted_revenue=("predicted_revenue_180d", "mean"),
            average_realized_revenue=(PUBLIC_TARGET_COLUMN, "mean"),
            realized_revenue=(PUBLIC_TARGET_COLUMN, "sum"),
        )
        .reset_index()
    )
    result["realized_value_share"] = result["realized_revenue"] / total
    return result


def run_public_validation(
    project_root: str | Path,
    config_path: str | Path | None = None,
) -> dict[str, Any]:
    """Fit, calibrate, evaluate, and report the licensed public-data model."""
    root = Path(project_root).resolve()
    selected_config = (
        Path(config_path) if config_path else root / "configs" / "public_validation.json"
    )
    config = load_public_validation_config(selected_config)
    snapshots_path = root / "data" / "external" / "processed" / "customer_snapshots.csv.gz"
    quality_path = root / "data" / "external" / "quality_report.json"
    if not snapshots_path.exists() or not quality_path.exists():
        raise FileNotFoundError(
            "Public inputs are missing. Run download_public_data.py and "
            "build_public_snapshots.py first."
        )
    snapshots = pd.read_csv(
        snapshots_path,
        dtype={"customer_id": "string", "country": "string", "snapshot_date": "string"},
    )
    train, selection, calibration, test = _split_snapshots(
        snapshots,
        config["selection_snapshot"],
        config["calibration_snapshot"],
        config["test_snapshot"],
    )
    selected_parameters, candidates = select_public_parameters(train, selection, config["seed"])
    development = pd.concat([train, selection], ignore_index=True)
    bundle = fit_public_model(development, selected_parameters, config["seed"])
    interval = calibrate_public_intervals(
        bundle,
        calibration,
        float(config["interval_target_coverage"]),
    )
    predictions = predict_public(bundle, test, interval)
    baseline = public_revenue_baseline(test)
    actual = test[PUBLIC_TARGET_COLUMN].to_numpy()
    model_metrics = regression_metrics(
        actual,
        predictions["predicted_revenue_180d"].to_numpy(),
        predictions["revenue_lower_80"].to_numpy(),
        predictions["revenue_upper_80"].to_numpy(),
    )
    raw_metrics = regression_metrics(
        actual,
        predictions["predicted_revenue_180d"].to_numpy(),
        predictions["revenue_lower_80_raw"].to_numpy(),
        predictions["revenue_upper_80_raw"].to_numpy(),
    )
    model_metrics["interval_80_raw_coverage"] = raw_metrics["interval_80_coverage"]
    model_metrics["interval_raw_mean_width"] = raw_metrics["interval_mean_width"]
    model_metrics["activity_average_precision"] = float(
        average_precision_score(test["future_active_180d"], predictions["active_probability_180d"])
    )
    model_metrics["activity_brier_score"] = float(
        brier_score_loss(test["future_active_180d"], predictions["active_probability_180d"])
    )
    baseline_metrics = regression_metrics(actual, baseline)
    bootstrap = paired_bootstrap_comparison(
        actual,
        predictions["predicted_revenue_180d"].to_numpy(),
        baseline,
        iterations=int(config["bootstrap_iterations"]),
        seed=int(config["seed"]),
    )
    scored = pd.concat(
        [
            test[["customer_id", "snapshot_date", PUBLIC_TARGET_COLUMN]].copy(),
            predictions,
        ],
        axis=1,
    )
    scored["baseline_revenue_180d"] = baseline
    scored["predicted_value_decile"] = pd.qcut(
        scored["predicted_revenue_180d"].rank(method="first"),
        10,
        labels=range(1, 11),
    )
    deciles = _decile_summary(scored)
    interval_by_decile = _interval_by_decile(scored)
    importance = public_permutation_importance(bundle, test, config["seed"])
    quality = json.loads(quality_path.read_text(encoding="utf-8"))
    observed_start = pd.Timestamp(quality["date_min"]).normalize()
    available_history_days = {
        snapshot_date: int((pd.Timestamp(snapshot_date) - observed_start).days)
        for snapshot_date in config["snapshot_dates"]
    }
    actual_total = float(actual.sum())
    predicted_total = float(predictions["predicted_revenue_180d"].sum())
    model_metrics["aggregate_prediction_to_actual_ratio"] = (
        predicted_total / actual_total if actual_total else 0.0
    )
    model_metrics["negative_prediction_rate"] = float(
        (predictions["predicted_revenue_180d"] < 0).mean()
    )
    model_metrics["negative_realized_value_rate"] = float((actual < 0).mean())
    metrics: dict[str, Any] = {
        "data": {
            "dataset": "UCI Online Retail II",
            "license": "CC BY 4.0",
            "synthetic": False,
            "source_rows": int(quality["source_rows"]),
            "usable_transaction_rows": int(quality["usable_rows"]),
            "customers": int(quality["customers"]),
            "invoices": int(quality["invoices"]),
            "countries": int(quality["countries"]),
            "date_min": quality["date_min"],
            "date_max": quality["date_max"],
            "cancellation_rows_retained": int(quality["cancellation_rows"]),
            "exact_duplicate_rows_removed": int(quality["exact_duplicate_rows"]),
            "missing_customer_rows_excluded": int(quality["missing_customer_rows"]),
            "other_invalid_rows_excluded": int(
                quality["excluded_rows"] - quality["missing_customer_rows"]
            ),
            "snapshot_rows": int(len(snapshots)),
            "snapshot_fingerprint": public_snapshot_fingerprint(snapshots),
            "lookback_coverage": {
                "required_days": int(config["lookback_days"]),
                "minimum_available_days": min(available_history_days.values()),
                "all_snapshots_complete": all(
                    days >= int(config["lookback_days"]) for days in available_history_days.values()
                ),
                "available_days_by_snapshot": available_history_days,
            },
        },
        "split": {
            "train_rows": int(len(train)),
            "selection_rows": int(len(selection)),
            "calibration_rows": int(len(calibration)),
            "test_rows": int(len(test)),
            "selection_snapshot": config["selection_snapshot"],
            "calibration_snapshot": config["calibration_snapshot"],
            "test_snapshot": config["test_snapshot"],
        },
        "model_selection": {
            "selected_parameters": selected_parameters,
            "candidates": candidates,
        },
        "holdout": {"model": model_metrics, "baseline": baseline_metrics},
        "bootstrap_comparison": {
            "iterations": int(config["bootstrap_iterations"]),
            "method": "paired customer-level resampling with replacement",
            "metrics": bootstrap,
        },
        "interval_calibration": asdict(interval),
        "conditional_interval": {
            "highest_value_decile_coverage": float(
                interval_by_decile.loc[
                    interval_by_decile["predicted_value_decile"] == 10,
                    "calibrated_coverage",
                ].iloc[0]
            ),
            "highest_value_decile_mean_width": float(
                interval_by_decile.loc[
                    interval_by_decile["predicted_value_decile"] == 10,
                    "calibrated_mean_width",
                ].iloc[0]
            ),
        },
        "decision_evidence": {
            "model_top_10_value_capture": model_metrics["top_10_value_capture"],
            "baseline_top_10_value_capture": baseline_metrics["top_10_value_capture"],
            "model_top_20_value_capture": model_metrics["top_20_value_capture"],
            "baseline_top_20_value_capture": baseline_metrics["top_20_value_capture"],
        },
        "publication_guardrail": {
            "row_level_customer_output_committed": False,
            "target": "signed 180-day net revenue",
            "not_available": ["contribution margin", "treatment cost", "causal uplift"],
        },
    }
    output = root / "reports" / "public_validation"
    create_public_reports(scored, deciles, interval_by_decile, importance, metrics, output)
    return metrics
