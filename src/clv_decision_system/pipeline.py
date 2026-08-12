"""End-to-end reproducible CLV workflow."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pandas as pd

from .config import load_config
from .evaluation import full_evaluation, interval_diagnostics, permutation_wape_importance
from .features import build_customer_snapshots
from .modeling import (
    FEATURES,
    baseline_prediction,
    calibrate_intervals,
    fit_final_model,
    predict,
    select_parameters,
)
from .policy import TIER_ORDER, apply_policy, policy_summary
from .reporting import create_reports
from .synthetic import generate_customers, generate_orders, public_customer_columns


def _write_csv(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)


def _data_fingerprint(*frames: pd.DataFrame) -> str:
    digest = hashlib.sha256()
    for frame in frames:
        values = pd.util.hash_pandas_object(frame, index=True).values
        digest.update(values.tobytes())
    return digest.hexdigest()[:16]


def _split_snapshots(
    snapshots: pd.DataFrame,
    selection_snapshot: str,
    calibration_snapshot: str,
    test_snapshot: str,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    train = snapshots[snapshots["snapshot_date"] < selection_snapshot].copy()
    selection = snapshots[snapshots["snapshot_date"] == selection_snapshot].copy()
    calibration = snapshots[snapshots["snapshot_date"] == calibration_snapshot].copy()
    test = snapshots[snapshots["snapshot_date"] == test_snapshot].copy()
    if train.empty or selection.empty or calibration.empty or test.empty:
        raise ValueError("Temporal split produced an empty partition")
    ordered_dates = [
        train["snapshot_date"].max(),
        selection["snapshot_date"].min(),
        calibration["snapshot_date"].min(),
        test["snapshot_date"].min(),
    ]
    if ordered_dates != sorted(ordered_dates) or len(set(ordered_dates)) != len(ordered_dates):
        raise ValueError("Training, selection, calibration, and test periods must be ordered")
    return train, selection, calibration, test


def run_pipeline(
    project_root: str | Path,
    config_path: str | Path | None = None,
) -> dict[str, Any]:
    """Run data generation, modeling, decision policy, and reporting."""
    root = Path(project_root).resolve()
    selected_config = Path(config_path) if config_path else root / "configs" / "pipeline.json"
    config = load_config(selected_config)

    customers_internal = generate_customers(config["n_customers"], config["seed"])
    orders = generate_orders(
        customers_internal,
        config["data_start"],
        config["data_end"],
        config["seed"],
    )
    customers = public_customer_columns(customers_internal)
    snapshots = build_customer_snapshots(
        customers,
        orders,
        config["snapshot_dates"],
        config["lookback_days"],
        config["horizon_days"],
        config["annual_discount_rate"],
        root / "sql",
    )
    fingerprint = _data_fingerprint(customers, orders, snapshots)

    train, selection, calibration, test = _split_snapshots(
        snapshots,
        config["selection_snapshot"],
        config["calibration_snapshot"],
        config["test_snapshot"],
    )
    selected_parameters, candidate_results = select_parameters(train, selection, config["seed"])
    development = pd.concat([train, selection], ignore_index=True)
    bundle = fit_final_model(development, selected_parameters, config["seed"])
    interval_calibration = calibrate_intervals(
        bundle,
        calibration,
        target_coverage=float(config["interval_target_coverage"]),
    )
    test_predictions = predict(bundle, test, interval_calibration)
    baseline = baseline_prediction(test)
    evaluations = full_evaluation(test, test_predictions, baseline)
    importance = permutation_wape_importance(bundle, test, FEATURES, config["seed"])

    raw_interval_predictions = test_predictions.copy()
    raw_interval_predictions["clv_lower_80"] = raw_interval_predictions["clv_lower_80_raw"]
    raw_interval_predictions["clv_upper_80"] = raw_interval_predictions["clv_upper_80_raw"]
    raw_decisions = apply_policy(raw_interval_predictions, config["policy"])
    decisions = apply_policy(test_predictions, config["policy"])
    decisions["high_uncertainty_raw"] = raw_decisions["high_uncertainty"]
    decisions["investment_ceiling_raw"] = raw_decisions["investment_ceiling"]
    scored = pd.concat(
        [
            test[["customer_id", "snapshot_date", "future_discounted_margin_180d"]],
            decisions,
        ],
        axis=1,
    )
    scored["baseline_clv_180d"] = baseline
    scored = scored.reset_index(drop=True)
    scored["predicted_value_decile"] = pd.qcut(
        scored["predicted_clv_180d"].rank(method="first"),
        10,
        labels=range(1, 11),
    )
    tiers = policy_summary(scored)
    interval_by_decile = interval_diagnostics(scored, "predicted_value_decile")
    interval_by_tier = interval_diagnostics(scored, "service_tier")
    interval_by_tier["service_tier"] = pd.Categorical(
        interval_by_tier["service_tier"],
        categories=TIER_ORDER,
        ordered=True,
    )
    interval_by_tier = interval_by_tier.sort_values("service_tier").reset_index(drop=True)

    model_improvement = 1 - evaluations["model"]["wape"] / evaluations["baseline"]["wape"]
    interval_calibration_metrics = {
        **asdict(interval_calibration),
        "raw_high_uncertainty_rate": float(raw_decisions["high_uncertainty"].mean()),
        "calibrated_high_uncertainty_rate": float(decisions["high_uncertainty"].mean()),
        "customers_newly_flagged_high_uncertainty": int(
            ((~raw_decisions["high_uncertainty"]) & decisions["high_uncertainty"]).sum()
        ),
        "raw_total_investment_ceiling": float(raw_decisions["investment_ceiling"].sum()),
        "calibrated_total_investment_ceiling": float(decisions["investment_ceiling"].sum()),
    }
    metrics: dict[str, Any] = {
        "data": {
            "synthetic": True,
            "customers": int(len(customers)),
            "orders": int(len(orders)),
            "snapshot_rows": int(len(snapshots)),
            "fingerprint": fingerprint,
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
            "candidates": candidate_results,
        },
        "holdout": evaluations,
        "interval_calibration": interval_calibration_metrics,
        "decision_evidence": {
            "relative_wape_reduction_vs_baseline": float(model_improvement),
            "protect_tier_realized_value_share": float(
                tiers.loc[tiers["service_tier"] == "protect", "realized_value_share"].iloc[0]
            ),
            "protect_tier_customer_share": float(
                tiers.loc[tiers["service_tier"] == "protect", "customer_share"].iloc[0]
            ),
        },
    }

    _write_csv(customers, root / "data" / "synthetic" / "customers.csv")
    _write_csv(orders, root / "data" / "synthetic" / "orders.csv")
    _write_csv(snapshots, root / "data" / "processed" / "customer_snapshots.csv")
    _write_csv(scored, root / "artifacts" / "holdout_customer_scores.csv")
    _write_csv(tiers, root / "artifacts" / "service_tier_summary.csv")
    _write_csv(importance, root / "artifacts" / "feature_importance.csv")
    _write_csv(interval_by_decile, root / "reports" / "interval_coverage_by_decile.csv")
    _write_csv(interval_by_tier, root / "reports" / "interval_coverage_by_tier.csv")
    model_metadata = {
        "model_type": "two-part histogram gradient boosting",
        "target": "180-day discounted contribution margin",
        "features": FEATURES,
        "selected_parameters": selected_parameters,
        "interval_calibration": interval_calibration_metrics,
        "data_fingerprint": fingerprint,
    }
    metadata_path = root / "artifacts" / "model_metadata.json"
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.write_text(
        json.dumps(model_metadata, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    create_reports(
        scored,
        tiers,
        importance,
        interval_by_decile,
        interval_by_tier,
        metrics,
        root / "reports",
    )
    return metrics
