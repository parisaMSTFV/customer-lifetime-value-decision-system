# Decision Policy

## Purpose

The model produces a continuous estimate. The policy converts that estimate into a capacity plan that a CRM or customer operations team can review and configure.

This policy applies only to the synthetic contribution-margin case. The UCI public
validation has no margin or treatment-cost fields, so its revenue ranking is not used to
transfer these investment ceilings.

| Tier | Population share | Default ceiling per customer | Operational interpretation |
|---|---:|---:|---|
| Protect | 10% | 24 | Highest predicted value; preserve service continuity and review high-uncertainty cases |
| Grow | 20% | 14 | Strong expected value; eligible for measured development programs |
| Nurture | 40% | 7 | Moderate expected value; use scalable engagement and experiments |
| Low Touch | 30% | 2 | Lower expected value; maintain efficient service and avoid unjustified spend |

Shares and caps are configuration, not discovered truths. They live in `configs/pipeline.json` and should change with real capacity, unit economics, and customer strategy.

## Tier assignment

Customers are sorted by `predicted_clv_180d`. Integer capacities are derived from all
four configured shares with a deterministic largest-remainder allocation, so every row
is assigned and the Low Touch share is enforced rather than inferred. Assignment uses no
realized holdout value.

## Investment ceiling

The default ceiling is:

\[
Ceiling_i = \max(0, \min(0.08 \times LowerBound_i, TierCap_i))
\]

Using the split-conformal lower interval bound makes the rule conservative, but the 8% fraction and tier caps are still scenario assumptions. The ceiling is a planning guardrail, not expected incremental profit. The raw quantile lower bound is retained in the scored artifact for audit but is not used by the active policy.

## Uncertainty review

`high_uncertainty` becomes true when interval width divided by the point prediction exceeds 1.25. High-value, high-uncertainty customers should be reviewed before expensive individual action. A wide interval does not automatically justify excluding or downgrading a customer.

## Holdout evidence

The Protect tier contains 10% of customers and 24.7% of realized 180-day contribution margin on the untouched synthetic holdout. This checks whether the ranking concentrates value. It does not estimate treatment response.

Calibration increased the high-uncertainty rate from 65.5% to 70.2% and reduced the aggregate investment ceiling from 3,712.1 to 3,372.3 synthetic currency units. Protect-tier interval coverage is 80.0%; conditional coverage elsewhere remains uneven, so high-value cases retain an explicit review requirement.

## Production controls

1. Approve the contribution margin definition with Finance.
2. Set tier capacity and caps from current operating constraints.
3. Monitor realized value and interval coverage by scoring period.
4. Randomize treatments within eligible tiers to measure causal uplift.
5. Keep a standard service floor independent of predicted value.
6. Provide manual review for high-cost or customer-sensitive decisions.
