# Model Card

## Model summary

| Item | Detail |
|---|---|
| Model | Two-part histogram gradient boosting with separate quantile models |
| Unit of prediction | Synthetic customer at a scoring snapshot |
| Target | Discounted contribution margin over the next 180 days |
| Data | Fully synthetic non-contractual ecommerce behavior |
| Validation | Blocked temporal validation and one untouched test snapshot |
| Primary metric | WAPE |
| Decision use | Relative prioritization and configurable service tiers |

## Intended use

- Compare customers on expected near-term contribution margin.
- Allocate limited review or service capacity by transparent relative tiers.
- Set conservative policy guardrails using a lower prediction bound.
- Demonstrate a reproducible CLV workflow before adapting it to approved business data.

## Out-of-scope use

- Claiming production accuracy from the synthetic metrics.
- Inferring the causal effect of a retention or marketing treatment.
- Making credit, employment, insurance, healthcare, or other high-stakes eligibility decisions.
- Using the score as the sole basis for excluding customers from essential support.
- Interpreting 180-day value as an unlimited lifetime estimate.

## Untouched holdout performance

| Metric | Model | Baseline |
|---|---:|---:|
| WAPE | 0.415 | 0.592 |
| MAE | 32.03 | 45.67 |
| RMSE | 46.19 | 68.94 |
| Spearman | 0.813 | 0.736 |
| Top 10% value capture | 24.4% | 22.4% |
| Top 20% value capture | 43.4% | 40.2% |

Additional model diagnostics:

- Activity average precision: 0.978.
- Activity Brier score: 0.080.
- Nominal 80% interval coverage: 74.0%.
- Mean interval width: 100.82 synthetic currency units.

## Important drivers

The project reports permutation importance as the increase in holdout WAPE when each feature is shuffled. This is global predictive importance, not a causal explanation. Results are stored in `artifacts/feature_importance.csv` and regenerated with the pipeline.

![Permutation importance](../reports/figures/feature_importance.png)

## Risks and monitoring

- **Calibration drift:** track interval coverage and activity Brier score by scoring month.
- **Ranking drift:** compare top-decile realized value capture with the baseline.
- **Data drift:** monitor recency, order frequency, margin, return, and acquisition-channel distributions.
- **Policy drift:** review tier capacity and investment caps separately from model retraining.
- **Selection effects:** treatment changes future observations; use experiments to measure intervention impact.

Before deployment, rebuild contribution margin definitions, exclude prohibited variables, test performance across relevant operational groups, calibrate uncertainty, document review rights, and establish a retraining threshold.

