# Methodology

## Analytical target

For each eligible customer at snapshot date \(t\), the target is discounted contribution margin from orders in the following 180 days:

\[
CLV_{i,t}^{180} = \sum_{o \in (t, t+180]} \frac{CM_o}{1 + r \cdot d_o / 365}
\]

where \(CM_o\) is order contribution margin, \(r=10\%\) is the configurable annual discount rate, and \(d_o\) is the number of days between the snapshot and order.

This target is practical for recurring ecommerce decisions. It is not an estimate of value over an unlimited customer lifetime.

## Synthetic population

The fixed-seed generator creates 1,400 non-contractual ecommerce customers and 51,327 orders from January 2022 through June 2025. Behavior includes acquisition context, heterogeneous purchase rates, lifecycle trends, seasonality, category breadth, discount use, returns, and contribution margin.

Latent generator segments and customer effects are removed before data is persisted. The model sees only fields that could plausibly be available at scoring time.

## Snapshot design

Features use a 365-day lookback and labels use the subsequent 180 days.

| Role | Snapshot date | Rows | Use |
|---|---:|---:|---|
| Training | 2023-06-30 and 2023-12-31 | 2,800 | Fit candidate models |
| Validation | 2024-06-30 | 1,400 | Select hyperparameters |
| Test | 2024-12-31 | 1,400 | Final untouched evaluation |

The same customers may appear at multiple dates because this represents a recurring scoring process. Separation is temporal: no order after a snapshot can enter its features, and the test date is not used for model selection.

## Feature engineering

`sql/customer_value_snapshot.sql` is executed by the pipeline. It produces:

- recency and tenure;
- order counts over 30, 90, 180, and 365 days;
- revenue and contribution margin windows;
- recent margin momentum;
- average order value, discount rate, and return rate;
- category breadth and active-month frequency;
- acquisition channel and broad synthetic region.

`sql/customer_value_label.sql` separately constructs the forward-looking target. Keeping feature and label windows explicit makes the temporal boundary testable.

## Models

The point estimate is a two-part hurdle model:

1. Histogram gradient boosting classifier for any activity in the next 180 days.
2. Histogram gradient boosting regressor for log margin among active outcomes.
3. Expected value equals activity probability multiplied by conditional margin.

Separate 10th- and 90th-quantile gradient boosting regressors provide the nominal 80% interval. Three small model configurations are compared on validation WAPE. The selected configuration is then refit on training plus validation before the single holdout evaluation.

## Baseline

The fixed RFM value baseline begins with trailing 180-day contribution margin and applies:

- exponential recency decay;
- a bounded ratio of recent 90-day margin to the previous 90-day margin.

It is intentionally simple enough for a stakeholder to reproduce and challenge.

## Evaluation

- **WAPE:** aggregate absolute error divided by aggregate actual value.
- **MAE and RMSE:** absolute and squared-error scale checks.
- **Spearman correlation:** quality of customer ranking.
- **Top-fraction value capture:** realized value held by the top 10% or 20% of scores.
- **Average precision and Brier score:** activity ranking and probability quality.
- **Interval coverage:** share of actual outcomes within the nominal 80% interval.

The holdout interval covered 74% of outcomes, so uncertainty is directionally useful but not yet production-calibrated.

## Reproducibility

The generator seed, feature windows, split dates, model candidates, and policy settings are versioned. CI regenerates the committed outputs on Python 3.11 and 3.12 and fails if tracked data, artifacts, or reports change. The expected fingerprint is `b24f3c2d959f40ea`.

