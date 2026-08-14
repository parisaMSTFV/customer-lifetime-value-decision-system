# Public external-validation report

## Scope

This report tests customer-value ranking on licensed UCI Online Retail II transactions. The target is 180-day net revenue, not contribution margin, profit, causal uplift, or unlimited lifetime value.

## Untouched June 2011 snapshot

- Model WAPE: **0.689**; baseline WAPE: **0.662**. Model error is **4.0% higher** than the fixed trailing-value baseline.
- Spearman rank correlation: **0.598**; baseline: **0.557**.
- Top 10% realized value capture: **61.9%**; baseline: **60.6%**.
- Top 20% realized value capture: **74.9%**; baseline: **72.6%**.
- Raw nominal 80% interval coverage: **87.8%**; split-conformal coverage: **87.8%**.
- The conformal correction was **£0.00**, fitted on **4,537** customers before the test snapshot.
- The highest predicted-value decile covered **75.9%**; marginal coverage is not a subgroup guarantee.

## Decision interpretation

Ranking evidence can support a capacity decision such as which customers receive manual review first. It cannot determine how much to spend on a customer because the public source has no margin or treatment-cost fields.

## Limitations

- The source represents one anonymous UK-based retailer with a mixed retail and wholesale customer base.
- Revenue is heavy-tailed, and prediction error must be read together with ranking and capacity metrics.
- Marginal interval calibration does not guarantee equal coverage by value decile, country, or future period.
- Historical value prediction does not identify a causal CRM treatment effect.
