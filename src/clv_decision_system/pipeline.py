"""End-to-end reproducible CLV workflow."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd

from .config import load_config
from .evaluation import full_evaluation, permutation_wape_importance
from .features import build_customer_snapshots
from .modeling import (
    FEATURES,
    baseline_prediction,
    fit_final_model,
    predict,
    select_parameters,
)
from .policy import apply_policy, policy_summary
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
    validation_snapshot: str,
    test_snapshot: str,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    train = snapshots[snapshots["snapshot_date"] < validation_snapshot].copy()
    validation = snapshots[snapshots["snapshot_date"] == validation_snapshot].copy()
    test = snapshots[snapshots["snapshot_date"] == test_snapshot].copy()
    if train.empty or validation.empty or test.empty:
        raise ValueError("Temporal split produced an empty partition")
    if train["snapshot_date"].max() >= validation["snapshot_date"].min():
        raise ValueError("Training snapshots overlap the validation period")
    if validation["snapshot_date"].max() >= test["snapshot_date"].min():
        raise ValueError("Validation snapshot is not earlier than the test snapshot")
    return train, validation, test


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

    train, validation, test = _split_snapshots(
        snapshots,
        config["validation_snapshot"],
        config["test_snapshot"],
    )
    selected_parameters, candidate_results = select_parameters(train, validation, config["seed"])
    development = pd.concat([train, validation], ignore_index=True)
    bundle = fit_final_model(development, selected_parameters, config["seed"])
    test_predictions = predict(bundle, test)
    baseline = baseline_prediction(test)
    evaluations = full_evaluation(test, test_predictions, baseline)
    importance = permutation_wape_importance(bundle, test, FEATURES, config["seed"])

    decisions = apply_policy(test_predictions, config["policy"])
    scored = pd.concat(
        [
            test[["customer_id", "snapshot_date", "future_discounted_margin_180d"]],
            decisions,
        ],
        axis=1,
    )
    scored["baseline_clv_180d"] = baseline
    scored = scored.reset_index(drop=True)
    tiers = policy_summary(scored)

    model_improvement = 1 - evaluations["model"]["wape"] / evaluations["baseline"]["wape"]
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
            "validation_rows": int(len(validation)),
            "test_rows": int(len(test)),
            "validation_snapshot": config["validation_snapshot"],
            "test_snapshot": config["test_snapshot"],
        },
        "model_selection": {
            "selected_parameters": selected_parameters,
            "candidates": candidate_results,
        },
        "holdout": evaluations,
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
    model_metadata = {
        "model_type": "two-part histogram gradient boosting",
        "target": "180-day discounted contribution margin",
        "features": FEATURES,
        "selected_parameters": selected_parameters,
        "data_fingerprint": fingerprint,
    }
    metadata_path = root / "artifacts" / "model_metadata.json"
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.write_text(
        json.dumps(model_metadata, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    create_reports(scored, tiers, importance, metrics, root / "reports")
    return metrics
