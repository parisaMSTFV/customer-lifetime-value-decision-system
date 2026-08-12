# CLV decision report

## Decision

Prioritize customers by expected discounted contribution margin over the next 180 days, then translate the ranking into transparent service tiers and conservative investment ceilings.

## Untouched holdout evidence

- Model WAPE: **0.421**, versus **0.592** for the recency-adjusted trailing-margin baseline (28.8% relative error reduction).
- Spearman rank correlation: **0.808**, versus **0.736** for the baseline.
- Top 10% realized value capture: **24.2%**.
- Empirical coverage of the raw nominal 80% interval: **71.4%**; after split-conformal calibration: **81.4%**.
- Calibration changed the high-uncertainty flag rate from **67.3%** to **70.1%** and changed the aggregate policy investment ceiling from **4220.8** to **3905.9** synthetic currency units.
- The Protect tier contains **10.0%** of customers and **24.2%** of realized holdout value.

## How to use the output

The score supports relative prioritization and service-level budgeting. `investment_ceiling` is a policy guardrail based on the lower prediction bound and a configurable value fraction. It is not an estimate of treatment uplift or causal ROI.

## Limitations

- All customers and orders are synthetic; the results validate the workflow, not production performance.
- The model estimates 180-day value, not an unlimited customer lifetime.
- Split-conformal calibration improves marginal coverage but does not guarantee equal coverage in every customer subgroup or after distribution shift.
- Treatment impact needs randomized experimentation or credible causal identification; CLV alone cannot supply it.
