# Methodology

## Analytical target

For each eligible customer at snapshot date \(t\), the target is discounted contribution margin from orders in the following 180 days:

\[
CLV_{i,t}^{180} = \sum_{o \in (t, t+180]} \frac{CM_o}{1 + r \cdot d_o / 365}
\]

where \(CM_o\) is order contribution margin, \(r=10\%\) is the configurable annual discount rate, and \(d_o\) is the number of days between the snapshot and order.

This target is practical for recurring ecommerce decisions. It is not an estimate of value over an unlimited customer lifetime.

## Synthetic population

The fixed-seed generator creates 1,400 non-contractual ecommerce customers and 51,327 orders from January 2022 through June 2025. Behavior includes acquisition context, heterogeneous purchase rates, lifecycle trends, seasonality, category breadth, discount use, returns, and signed contribution margin. Loss-making orders are retained rather than floored to a positive value.

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

1. Histogram gradient boosting classifier for any value-bearing transaction in the next 180 days.
2. Squared-error histogram gradient boosting regressor for signed margin on its original
   scale among active outcomes.
3. Expected value equals activity probability multiplied by conditional mean margin.

The original-scale conditional mean avoids retransformation bias from exponentiating a
log-scale point prediction. An active customer can still have negative net margin.

Separate 10th- and 90th-quantile gradient boosting regressors provide the raw nominal 80% interval. Three small model configurations are compared on model-selection WAPE. The selected configuration is refit on training plus model-selection data. A later, dedicated calibration snapshot then fits a conservative split-conformal correction before the final holdout is opened.

For calibration row \(i\), the conformity score is:

\[
s_i = \max(\hat{q}_{0.10,i} - y_i, y_i - \hat{q}_{0.90,i})
\]

The finite-sample 80th percentile of these scores is added to the upper bound and subtracted from the lower bound, with a non-negative correction so calibration can widen but not shrink the raw interval. The correction is 4.39 synthetic currency units in the committed run.

## Baseline

The fixed RFM value baseline begins with trailing 180-day contribution margin and applies:

- exponential recency decay;
- a bounded, signed change between recent 90-day margin and the previous 90-day margin,
  normalized by their absolute scale.

It is intentionally simple enough for a stakeholder to reproduce and challenge.

## Evaluation

- **WAPE:** aggregate absolute error divided by aggregate absolute actual value.
- **MAE and RMSE:** absolute and squared-error scale checks.
- **Spearman correlation:** quality of customer ranking.
- **Top-fraction value capture:** realized value held by the top 10% or 20% of scores.
- **Average precision and Brier score:** activity ranking and probability quality.
- **Raw and calibrated interval coverage:** share of actual outcomes within each interval.
- **Conditional interval diagnostics:** coverage and width by predicted-value decile and service tier.

The raw holdout interval covered 75.0% of outcomes; the calibrated interval covered 82.6%. Conditional coverage remains uneven—the minimum predicted-value-decile coverage is 75.7%—so the marginal result is not presented as a subgroup guarantee.

## Reproducibility

The generator seed, feature windows, four-way split dates, interval target, model candidates, and policy settings are versioned. CI regenerates the committed outputs on Python 3.11 and 3.12 and fails if tracked data, artifacts, or reports change. The expected fingerprint is `7feb745524f4f82b`.

## Licensed public external validation

The companion validation uses UCI Online Retail II under CC BY 4.0. It is intentionally
separate from the synthetic contribution-margin policy: the public source has revenue
and cancellations, but no cost, margin, marketing-treatment, or causal-outcome fields.

### Contract and temporal design

- The official archive is verified against a pinned SHA-256 before extraction.
- DuckDB enforces a typed transaction contract and builds five customer snapshots.
- Features use transactions strictly before the scoring date; labels use the following
  180 days. A SQL/Pandas parity test checks the boundary on a hand-built fixture.
- Exact duplicates are removed, missing customer identifiers are excluded, and
  cancellations remain negative signed revenue. Every exclusion is counted.
- Signed returns remain in both historical revenue features and the customer-level
  180-day net-revenue target. Activity is defined independently as any future transaction
  line, including a cancellation, so zero activity implies zero target value.
- The earliest snapshot has 396 days of observed source history, exceeding the required
  365-day lookback. Construction fails if any configured snapshot is incomplete.

| Role | Snapshot date | Rows |
|---|---:|---:|
| Training | 2011-01-01 and 2011-02-01 | 8,755 |
| Model selection | 2011-03-01 | 4,537 |
| Interval calibration | 2011-04-01 | 4,716 |
| Untouched test | 2011-06-01 | 4,933 |

The public model uses the same explainable two-part logic: activity probability
multiplied by original-scale conditional mean signed revenue, with separate quantile
models and a split-conformal widening step. A recency-adjusted signed trailing
180-day net-revenue rule is fixed as the baseline before the test is opened.

### Executed result

The public test is mixed and is reported without selection after the fact. The baseline
has lower WAPE (0.653 versus 0.672), while the model has higher Spearman correlation
(0.611 versus 0.546) and captures more realized value in the top 10% (62.7% versus
60.9%) and top 20% (75.8% versus 73.1%).

A 1,000-iteration paired customer bootstrap puts the top-10 capture difference at
+1.8 percentage points (95% CI +0.5 to +3.0) and the top-20 difference at +2.8 points
(95% CI +1.3 to +4.3). The WAPE difference is +0.019 for model minus baseline (95% CI
-0.011 to +0.047), so point-error superiority is not claimed. Aggregate predictions
equal 64.5% of aggregate realized signed revenue, which remains a disclosed calibration
limitation.

The raw interval already covered 86.8% of the calibration snapshot, so the non-negative
conformal correction is correctly £0. On the untouched test, raw and calibrated marginal
coverage are both 80.1%. Coverage falls to 65.8% in the highest predicted-value decile,
which prevents a subgroup guarantee. Results are decision evidence for ranking under
capacity; they do not justify a spend ceiling or treatment recommendation.

The public snapshot fingerprint is `4357171d0faf1887`. Raw data and row-level customer
scores are not committed; the repository publishes only aggregate tables, figures, and
machine-readable metrics.
