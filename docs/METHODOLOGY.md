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
| Training | 2023-06-30 | 1,400 | Fit candidate models |
| Model selection | 2023-12-31 | 1,400 | Select hyperparameters |
| Interval calibration | 2024-06-30 | 1,400 | Fit the split-conformal correction |
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

Separate 10th- and 90th-quantile gradient boosting regressors provide the raw nominal 80% interval. Three small model configurations are compared on model-selection WAPE. The selected configuration is refit on training plus model-selection data. A later, dedicated calibration snapshot then fits a conservative split-conformal correction before the final holdout is opened.

For calibration row \(i\), the conformity score is:

\[
s_i = \max(\hat{q}_{0.10,i} - y_i, y_i - \hat{q}_{0.90,i})
\]

The finite-sample 80th percentile of these scores is added to the upper bound and subtracted from the lower bound, with a non-negative correction so calibration can widen but not shrink the raw interval. The correction is 3.48 synthetic currency units in the committed run.

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
- **Raw and calibrated interval coverage:** share of actual outcomes within each interval.
- **Conditional interval diagnostics:** coverage and width by predicted-value decile and service tier.

The raw holdout interval covered 71.4% of outcomes; the calibrated interval covered 81.4%. Conditional coverage remains uneven—the Protect tier and highest predicted-value decile each covered 74.3%—so the marginal result is not presented as a subgroup guarantee.

## Reproducibility

The generator seed, feature windows, four-way split dates, interval target, model candidates, and policy settings are versioned. CI regenerates the committed outputs on Python 3.11 and 3.12 and fails if tracked data, artifacts, or reports change. The expected fingerprint is `b24f3c2d959f40ea`.
