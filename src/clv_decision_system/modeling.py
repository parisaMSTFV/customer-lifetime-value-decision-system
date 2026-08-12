"""Temporal model selection and two-part CLV estimation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OrdinalEncoder

TARGET_COLUMN = "future_discounted_margin_180d"
ACTIVE_COLUMN = "future_active_180d"
CATEGORICAL_FEATURES = ["acquisition_channel", "region"]
NUMERIC_FEATURES = [
    "tenure_days",
    "recency_days",
    "orders_30d",
    "orders_90d",
    "orders_180d",
    "orders_365d",
    "revenue_90d",
    "revenue_180d",
    "revenue_365d",
    "margin_90d",
    "margin_previous_90d",
    "margin_180d",
    "margin_365d",
    "average_order_value_365d",
    "average_discount_365d",
    "return_rate_365d",
    "category_diversity_365d",
    "active_months_365d",
    "margin_momentum_90d",
    "recent_order_share",
]
FEATURES = CATEGORICAL_FEATURES + NUMERIC_FEATURES


MODEL_CANDIDATES = [
    {"max_leaf_nodes": 15, "learning_rate": 0.06, "min_samples_leaf": 25},
    {"max_leaf_nodes": 31, "learning_rate": 0.045, "min_samples_leaf": 35},
    {"max_leaf_nodes": 9, "learning_rate": 0.08, "min_samples_leaf": 20},
]


@dataclass
class ModelBundle:
    """Fitted preprocessing, point, and interval models."""

    preprocessor: ColumnTransformer
    classifier: HistGradientBoostingClassifier
    conditional_regressor: HistGradientBoostingRegressor
    lower_regressor: HistGradientBoostingRegressor
    upper_regressor: HistGradientBoostingRegressor
    parameters: dict[str, Any]


@dataclass(frozen=True)
class IntervalCalibration:
    """Split-conformal correction fitted on a dedicated temporal snapshot."""

    target_coverage: float
    correction: float
    calibration_rows: int
    raw_coverage: float
    calibrated_coverage: float


def make_preprocessor() -> ColumnTransformer:
    """Create a dense, reproducible preprocessing graph."""
    categorical_pipeline = Pipeline(
        [
            ("imputer", SimpleImputer(strategy="most_frequent")),
            (
                "encoder",
                OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1),
            ),
        ]
    )
    numeric_pipeline = Pipeline([("imputer", SimpleImputer(strategy="median"))])
    return ColumnTransformer(
        [
            ("categorical", categorical_pipeline, CATEGORICAL_FEATURES),
            ("numeric", numeric_pipeline, NUMERIC_FEATURES),
        ],
        sparse_threshold=0.0,
    )


def _fit_point_models(
    transformed_features: np.ndarray,
    target: pd.Series,
    active: pd.Series,
    parameters: dict[str, Any],
    seed: int,
) -> tuple[HistGradientBoostingClassifier, HistGradientBoostingRegressor]:
    common = {
        **parameters,
        "max_iter": 180,
        "l2_regularization": 1.0,
        "random_state": seed,
    }
    classifier = HistGradientBoostingClassifier(**common)
    classifier.fit(transformed_features, active)

    active_mask = active.to_numpy(dtype=bool)
    conditional_regressor = HistGradientBoostingRegressor(loss="squared_error", **common)
    conditional_regressor.fit(
        transformed_features[active_mask],
        np.log1p(target.to_numpy()[active_mask]),
    )
    return classifier, conditional_regressor


def _point_prediction(
    classifier: HistGradientBoostingClassifier,
    conditional_regressor: HistGradientBoostingRegressor,
    transformed_features: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    active_probability = classifier.predict_proba(transformed_features)[:, 1]
    conditional_margin = np.expm1(conditional_regressor.predict(transformed_features))
    prediction = np.clip(active_probability * conditional_margin, 0.0, None)
    return prediction, active_probability


def wape(actual: np.ndarray, predicted: np.ndarray) -> float:
    """Weighted absolute percentage error with a safe zero denominator."""
    denominator = float(np.abs(actual).sum())
    return float(np.abs(actual - predicted).sum() / denominator) if denominator else 0.0


def select_parameters(
    train: pd.DataFrame,
    validation: pd.DataFrame,
    seed: int,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Select hyperparameters on the dedicated validation snapshot only."""
    preprocessor = make_preprocessor()
    train_features = preprocessor.fit_transform(train[FEATURES])
    validation_features = preprocessor.transform(validation[FEATURES])
    candidate_results: list[dict[str, Any]] = []

    for parameters in MODEL_CANDIDATES:
        classifier, regressor = _fit_point_models(
            train_features,
            train[TARGET_COLUMN],
            train[ACTIVE_COLUMN],
            parameters,
            seed,
        )
        prediction, _ = _point_prediction(classifier, regressor, validation_features)
        score = wape(validation[TARGET_COLUMN].to_numpy(), prediction)
        candidate_results.append({**parameters, "validation_wape": score})

    best = min(candidate_results, key=lambda item: item["validation_wape"])
    selected = {key: best[key] for key in MODEL_CANDIDATES[0]}
    return selected, candidate_results


def fit_final_model(
    development: pd.DataFrame,
    parameters: dict[str, Any],
    seed: int,
) -> ModelBundle:
    """Refit selected models on train plus validation data."""
    preprocessor = make_preprocessor()
    transformed = preprocessor.fit_transform(development[FEATURES])
    classifier, conditional_regressor = _fit_point_models(
        transformed,
        development[TARGET_COLUMN],
        development[ACTIVE_COLUMN],
        parameters,
        seed,
    )
    common = {
        **parameters,
        "max_iter": 180,
        "l2_regularization": 1.0,
        "random_state": seed,
    }
    lower_regressor = HistGradientBoostingRegressor(loss="quantile", quantile=0.10, **common)
    upper_regressor = HistGradientBoostingRegressor(loss="quantile", quantile=0.90, **common)
    lower_regressor.fit(transformed, development[TARGET_COLUMN])
    upper_regressor.fit(transformed, development[TARGET_COLUMN])

    return ModelBundle(
        preprocessor=preprocessor,
        classifier=classifier,
        conditional_regressor=conditional_regressor,
        lower_regressor=lower_regressor,
        upper_regressor=upper_regressor,
        parameters=parameters,
    )


def predict(
    bundle: ModelBundle,
    frame: pd.DataFrame,
    interval_calibration: IntervalCalibration | None = None,
) -> pd.DataFrame:
    """Generate point estimates plus raw and optionally calibrated 80% intervals."""
    transformed = bundle.preprocessor.transform(frame[FEATURES])
    point, active_probability = _point_prediction(
        bundle.classifier,
        bundle.conditional_regressor,
        transformed,
    )
    raw_lower = np.clip(bundle.lower_regressor.predict(transformed), 0.0, None)
    raw_upper = np.clip(bundle.upper_regressor.predict(transformed), 0.0, None)
    raw_lower = np.minimum(raw_lower, point)
    raw_upper = np.maximum(raw_upper, point)
    correction = 0.0 if interval_calibration is None else interval_calibration.correction
    lower = np.minimum(np.clip(raw_lower - correction, 0.0, None), point)
    upper = np.maximum(raw_upper + correction, point)
    return pd.DataFrame(
        {
            "predicted_clv_180d": point,
            "active_probability_180d": active_probability,
            "clv_lower_80_raw": raw_lower,
            "clv_upper_80_raw": raw_upper,
            "clv_lower_80": lower,
            "clv_upper_80": upper,
        },
        index=frame.index,
    )


def calibrate_intervals(
    bundle: ModelBundle,
    calibration_frame: pd.DataFrame,
    target_coverage: float = 0.80,
) -> IntervalCalibration:
    """Fit a conservative split-conformal correction without using the test period."""
    if not 0.0 < target_coverage < 1.0:
        raise ValueError("target_coverage must be strictly between zero and one")
    if calibration_frame.empty:
        raise ValueError("calibration_frame must contain at least one row")

    predictions = predict(bundle, calibration_frame)
    actual = calibration_frame[TARGET_COLUMN].to_numpy()
    raw_lower = predictions["clv_lower_80_raw"].to_numpy()
    raw_upper = predictions["clv_upper_80_raw"].to_numpy()
    conformity_scores = np.maximum(raw_lower - actual, actual - raw_upper)
    rows = len(conformity_scores)
    finite_sample_quantile = min(1.0, np.ceil((rows + 1) * target_coverage) / rows)
    correction = max(
        0.0,
        float(np.quantile(conformity_scores, finite_sample_quantile, method="higher")),
    )
    calibrated_lower = np.clip(raw_lower - correction, 0.0, None)
    calibrated_upper = raw_upper + correction
    return IntervalCalibration(
        target_coverage=target_coverage,
        correction=correction,
        calibration_rows=rows,
        raw_coverage=float(np.mean((actual >= raw_lower) & (actual <= raw_upper))),
        calibrated_coverage=float(
            np.mean((actual >= calibrated_lower) & (actual <= calibrated_upper))
        ),
    )


def baseline_prediction(frame: pd.DataFrame) -> np.ndarray:
    """Transparent recency-adjusted trailing-margin baseline."""
    recency_weight = np.exp(-frame["recency_days"].to_numpy() / 220.0)
    momentum = np.clip(
        (frame["margin_90d"].to_numpy() + 10.0) / (frame["margin_previous_90d"].to_numpy() + 10.0),
        0.55,
        1.45,
    )
    return np.clip(frame["margin_180d"].to_numpy() * recency_weight * momentum, 0.0, None)
