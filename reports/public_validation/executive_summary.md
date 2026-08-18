# Public external-validation report

## Scope

This report tests customer-value ranking on licensed UCI Online Retail II transactions. The target is signed 180-day net revenue, not contribution margin, profit, causal uplift, or unlimited lifetime value.

## Untouched June 2011 snapshot

- Model WAPE: **0.672**; baseline WAPE: **0.653**. Model error is **2.9% higher** than the fixed trailing-value baseline.
- Spearman rank correlation: **0.611**; baseline: **0.546**.
- Top 10% realized value capture: **62.7%**; baseline: **60.9%**. Paired-bootstrap difference: **+1.8 percentage points** (95% CI **+0.5 to +3.0 points**).
- Top 20% realized value capture: **75.8%**; baseline: **73.1%**. Paired-bootstrap difference: **+2.8 percentage points** (95% CI **+1.3 to +4.3 points**).
- Paired-bootstrap WAPE difference (model minus baseline): **+0.019** (95% CI **-0.011 to +0.047**).
- Aggregate predicted-to-realized value ratio: **64.5%**; signed returns are retained rather than floored to zero.
- Raw nominal 80% interval coverage: **80.1%**; split-conformal coverage: **80.1%**.
- The conformal correction was **£0.00**, fitted on **4,716** customers before the test snapshot.
- The highest predicted-value decile covered **65.8%**; marginal coverage is not a subgroup guarantee.

## Decision interpretation

Ranking evidence can support a capacity decision such as which customers receive manual review first. It cannot determine how much to spend on a customer because the public source has no margin or treatment-cost fields.

## Limitations

- The source represents one anonymous UK-based retailer with a mixed retail and wholesale customer base.
- Revenue is heavy-tailed, and prediction error must be read together with ranking and capacity metrics.
- Bootstrap intervals quantify sampling uncertainty in this holdout; they do not cover temporal, retailer, or policy-transfer uncertainty.
- Marginal interval calibration does not guarantee equal coverage by value decile, country, or future period.
- Historical value prediction does not identify a causal CRM treatment effect.
