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


def predict(bundle: ModelBundle, frame: pd.DataFrame) -> pd.DataFrame:
    """Generate non-negative point estimates and ordered 80% prediction intervals."""
    transformed = bundle.preprocessor.transform(frame[FEATURES])
    point, active_probability = _point_prediction(
        bundle.classifier,
        bundle.conditional_regressor,
        transformed,
    )
    raw_lower = np.clip(bundle.lower_regressor.predict(transformed), 0.0, None)
    raw_upper = np.clip(bundle.upper_regressor.predict(transformed), 0.0, None)
    lower = np.minimum(raw_lower, point)
    upper = np.maximum(raw_upper, point)
    return pd.DataFrame(
        {
            "predicted_clv_180d": point,
            "active_probability_180d": active_probability,
            "clv_lower_80": lower,
            "clv_upper_80": upper,
        },
        index=frame.index,
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
