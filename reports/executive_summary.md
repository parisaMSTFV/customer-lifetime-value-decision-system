# CLV decision report

## Decision

Prioritize customers by expected discounted contribution margin over the next 180 days, then translate the ranking into transparent service tiers and conservative investment ceilings.

## Untouched holdout evidence

- Model WAPE: **0.415**, versus **0.592** for the recency-adjusted trailing-margin baseline (29.9% relative error reduction).
- Spearman rank correlation: **0.813**, versus **0.736** for the baseline.
- Top 10% realized value capture: **24.4%**.
- Empirical coverage of the nominal 80% interval: **74.0%**.
- The Protect tier contains **10.0%** of customers and **24.4%** of realized holdout value.

## How to use the output

The score supports relative prioritization and service-level budgeting. `investment_ceiling` is a policy guardrail based on the lower prediction bound and a configurable value fraction. It is not an estimate of treatment uplift or causal ROI.

## Limitations

- All customers and orders are synthetic; the results validate the workflow, not production performance.
- The model estimates 180-day value, not an unlimited customer lifetime.
- Prediction intervals are empirical model outputs and may require recalibration after a distribution shift.
- Treatment impact needs randomized experimentation or credible causal identification; CLV alone cannot supply it.
