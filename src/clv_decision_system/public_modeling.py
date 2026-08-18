"""Two-part value model used only for licensed public-data validation."""

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

from .modeling import IntervalCalibration, wape
from .public_features import (
    PUBLIC_ACTIVE_COLUMN,
    PUBLIC_CATEGORICAL_FEATURES,
    PUBLIC_FEATURES,
    PUBLIC_NUMERIC_FEATURES,
    PUBLIC_TARGET_COLUMN,
)

PUBLIC_MODEL_CANDIDATES = [
    {"max_leaf_nodes": 15, "learning_rate": 0.05, "min_samples_leaf": 35},
    {"max_leaf_nodes": 31, "learning_rate": 0.035, "min_samples_leaf": 55},
    {"max_leaf_nodes": 9, "learning_rate": 0.07, "min_samples_leaf": 25},
]


@dataclass
class PublicModelBundle:
    """Fitted preprocessing, hurdle, and quantile models for public revenue."""

    preprocessor: ColumnTransformer
    classifier: HistGradientBoostingClassifier
    conditional_regressor: HistGradientBoostingRegressor
    lower_regressor: HistGradientBoostingRegressor
    upper_regressor: HistGradientBoostingRegressor
    parameters: dict[str, Any]


def make_public_preprocessor() -> ColumnTransformer:
    """Build the public feature transformation without private business fields."""
    categorical = Pipeline(
        [
            ("imputer", SimpleImputer(strategy="most_frequent")),
            (
                "encoder",
                OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1),
            ),
        ]
    )
    numeric = Pipeline([("imputer", SimpleImputer(strategy="median"))])
    return ColumnTransformer(
        [
            ("categorical", categorical, PUBLIC_CATEGORICAL_FEATURES),
            ("numeric", numeric, PUBLIC_NUMERIC_FEATURES),
        ],
        sparse_threshold=0.0,
    )


def _fit_point_models(
    transformed: np.ndarray,
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
    classifier.fit(transformed, active)
    active_mask = active.to_numpy(dtype=bool)
    if active_mask.sum() < 2:
        raise ValueError("Public development data has too few active outcomes")
    conditional = HistGradientBoostingRegressor(loss="squared_error", **common)
    conditional.fit(transformed[active_mask], target.to_numpy()[active_mask])
    return classifier, conditional


def _point_prediction(
    classifier: HistGradientBoostingClassifier,
    conditional: HistGradientBoostingRegressor,
    transformed: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    active_probability = classifier.predict_proba(transformed)[:, 1]
    conditional_revenue = conditional.predict(transformed)
    prediction = active_probability * conditional_revenue
    return prediction, active_probability


def select_public_parameters(
    train: pd.DataFrame,
    validation: pd.DataFrame,
    seed: int,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Select one predeclared model configuration on the selection snapshot."""
    preprocessor = make_public_preprocessor()
    train_features = preprocessor.fit_transform(train[PUBLIC_FEATURES])
    validation_features = preprocessor.transform(validation[PUBLIC_FEATURES])
    results: list[dict[str, Any]] = []
    for parameters in PUBLIC_MODEL_CANDIDATES:
        classifier, conditional = _fit_point_models(
            train_features,
            train[PUBLIC_TARGET_COLUMN],
            train[PUBLIC_ACTIVE_COLUMN],
            parameters,
            seed,
        )
        prediction, _ = _point_prediction(classifier, conditional, validation_features)
        results.append(
            {
                **parameters,
                "selection_wape": wape(validation[PUBLIC_TARGET_COLUMN].to_numpy(), prediction),
            }
        )
    best = min(results, key=lambda item: item["selection_wape"])
    selected = {key: best[key] for key in PUBLIC_MODEL_CANDIDATES[0]}
    return selected, results


def fit_public_model(
    development: pd.DataFrame,
    parameters: dict[str, Any],
    seed: int,
) -> PublicModelBundle:
    """Fit the public point and raw interval models after model selection."""
    preprocessor = make_public_preprocessor()
    transformed = preprocessor.fit_transform(development[PUBLIC_FEATURES])
    classifier, conditional = _fit_point_models(
        transformed,
        development[PUBLIC_TARGET_COLUMN],
        development[PUBLIC_ACTIVE_COLUMN],
        parameters,
        seed,
    )
    common = {
        **parameters,
        "max_iter": 180,
        "l2_regularization": 1.0,
        "random_state": seed,
    }
    lower = HistGradientBoostingRegressor(loss="quantile", quantile=0.10, **common)
    upper = HistGradientBoostingRegressor(loss="quantile", quantile=0.90, **common)
    lower.fit(transformed, development[PUBLIC_TARGET_COLUMN])
    upper.fit(transformed, development[PUBLIC_TARGET_COLUMN])
    return PublicModelBundle(
        preprocessor=preprocessor,
        classifier=classifier,
        conditional_regressor=conditional,
        lower_regressor=lower,
        upper_regressor=upper,
        parameters=parameters,
    )


def predict_public(
    bundle: PublicModelBundle,
    frame: pd.DataFrame,
    interval_calibration: IntervalCalibration | None = None,
) -> pd.DataFrame:
    """Predict 180-day public net revenue and raw/calibrated intervals."""
    transformed = bundle.preprocessor.transform(frame[PUBLIC_FEATURES])
    point, active_probability = _point_prediction(
        bundle.classifier,
        bundle.conditional_regressor,
        transformed,
    )
    raw_lower = bundle.lower_regressor.predict(transformed)
    raw_upper = bundle.upper_regressor.predict(transformed)
    raw_lower = np.minimum(raw_lower, point)
    raw_upper = np.maximum(raw_upper, point)
    correction = 0.0 if interval_calibration is None else interval_calibration.correction
    lower = np.minimum(raw_lower - correction, point)
    upper = np.maximum(raw_upper + correction, point)
    return pd.DataFrame(
        {
            "predicted_revenue_180d": point,
            "active_probability_180d": active_probability,
            "revenue_lower_80_raw": raw_lower,
            "revenue_upper_80_raw": raw_upper,
            "revenue_lower_80": lower,
            "revenue_upper_80": upper,
        },
        index=frame.index,
    )


def calibrate_public_intervals(
    bundle: PublicModelBundle,
    calibration_frame: pd.DataFrame,
    target_coverage: float,
) -> IntervalCalibration:
    """Fit one split-conformal widening correction on a later public snapshot."""
    if not 0.0 < target_coverage < 1.0:
        raise ValueError("target_coverage must be strictly between zero and one")
    predictions = predict_public(bundle, calibration_frame)
    actual = calibration_frame[PUBLIC_TARGET_COLUMN].to_numpy()
    raw_lower = predictions["revenue_lower_80_raw"].to_numpy()
    raw_upper = predictions["revenue_upper_80_raw"].to_numpy()
    scores = np.maximum(raw_lower - actual, actual - raw_upper)
    rows = len(scores)
    finite_quantile = min(1.0, np.ceil((rows + 1) * target_coverage) / rows)
    correction = max(0.0, float(np.quantile(scores, finite_quantile, method="higher")))
    calibrated_lower = raw_lower - correction
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


def public_revenue_baseline(frame: pd.DataFrame) -> np.ndarray:
    """Recency-adjusted trailing-net-revenue baseline fixed before test evaluation."""
    recency_weight = np.exp(-frame["recency_days"].to_numpy() / 220.0)
    recent = frame["net_revenue_90d"].to_numpy()
    previous = frame["net_revenue_previous_90d"].to_numpy()
    normalized_change = np.clip(
        (recent - previous) / (np.abs(recent) + np.abs(previous) + 1.0),
        -0.5,
        0.5,
    )
    return frame["net_revenue_180d"].to_numpy() * recency_weight * (1.0 + normalized_change)


def public_permutation_importance(
    bundle: PublicModelBundle,
    frame: pd.DataFrame,
    seed: int,
) -> pd.DataFrame:
    """Report predictive WAPE sensitivity, not causal feature effects."""
    rng = np.random.default_rng(seed)
    actual = frame[PUBLIC_TARGET_COLUMN].to_numpy()
    reference = wape(actual, predict_public(bundle, frame)["predicted_revenue_180d"].to_numpy())
    rows: list[dict[str, float | str]] = []
    for feature in PUBLIC_FEATURES:
        shuffled = frame.copy()
        shuffled[feature] = rng.permutation(shuffled[feature].to_numpy())
        score = wape(
            actual,
            predict_public(bundle, shuffled)["predicted_revenue_180d"].to_numpy(),
        )
        rows.append({"feature": feature, "wape_increase": max(0.0, score - reference)})
    return pd.DataFrame(rows).sort_values("wape_increase", ascending=False).reset_index(drop=True)
