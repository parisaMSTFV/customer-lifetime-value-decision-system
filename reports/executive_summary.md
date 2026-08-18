# CLV decision report

## Decision

Prioritize customers by expected discounted contribution margin over the next 180 days, then translate the ranking into transparent service tiers and conservative investment ceilings.

## Untouched holdout evidence

- Model WAPE: **0.500**, versus **0.598** for the recency-adjusted trailing-margin baseline (16.4% relative error reduction).
- Spearman rank correlation: **0.788**, versus **0.718** for the baseline.
- Top 10% realized value capture: **24.7%**.
- Empirical coverage of the raw nominal 80% interval: **75.0%**; after split-conformal calibration: **82.6%**.
- Calibration changed the high-uncertainty flag rate from **65.5%** to **70.2%** and changed the aggregate policy investment ceiling from **3712.1** to **3372.3** synthetic currency units.
- The Protect tier contains **10.0%** of customers and **24.7%** of realized holdout value.
- Aggregate predicted value is **117.4%** of realized value; **4.1%** of customers have negative realized signed margin.

## How to use the output

The score supports relative prioritization and service-level budgeting. `investment_ceiling` is a policy guardrail based on the lower prediction bound and a configurable value fraction. It is not an estimate of treatment uplift or causal ROI.

## Limitations

- All customers and orders are synthetic; the results validate the workflow, not production performance.
- The model estimates 180-day value, not an unlimited customer lifetime.
- Split-conformal calibration improves marginal coverage but does not guarantee equal coverage in every customer subgroup or after distribution shift.
- Treatment impact needs randomized experimentation or credible causal identification; CLV alone cannot supply it.
