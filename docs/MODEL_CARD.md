# Model Card

## Model summary

| Item | Detail |
|---|---|
| Model | Two-part histogram gradient boosting with separate quantile models |
| Unit of prediction | Synthetic customer at a scoring snapshot |
| Target | Discounted contribution margin over the next 180 days |
| Data | Fully synthetic non-contractual ecommerce behavior |
| Validation | Blocked model selection, dedicated interval calibration, and one untouched test snapshot |
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
| WAPE | 0.500 | 0.598 |
| MAE | 36.36 | 43.48 |
| RMSE | 50.84 | 64.94 |
| Spearman | 0.788 | 0.718 |
| Top 10% value capture | 24.7% | 23.2% |
| Top 20% value capture | 43.0% | 41.1% |

Additional model diagnostics:

- Activity average precision: 0.978.
- Activity Brier score: 0.079.
- Raw nominal 80% interval coverage: 75.0%; mean width: 102.27.
- Split-conformal 80% interval coverage: 82.6%; mean width: 111.05.
- Protect-tier and highest-decile calibrated coverage: 80.0%; the minimum decile is 75.7%, so marginal calibration does not guarantee equal conditional coverage.
- Aggregate predicted value is 117.4% of aggregate realized value; 4.1% of customers have negative realized signed margin.
- Calibration increased the high-uncertainty flag rate from 65.5% to 70.2% and reduced the aggregate investment ceiling from 3,712.1 to 3,372.3 synthetic currency units.

## Important drivers

The project reports permutation importance as the increase in holdout WAPE when each feature is shuffled. This is global predictive importance, not a causal explanation. Results are stored in `artifacts/feature_importance.csv` and regenerated with the pipeline.

![Permutation importance](../reports/figures/feature_importance.png)

## Risks and monitoring

- **Calibration drift:** track aggregate value calibration, raw and calibrated interval coverage, and activity Brier score by scoring month.
- **Conditional undercoverage:** review coverage by value decile and service tier; the committed Protect-tier result remains below target.
- **Ranking drift:** compare top-decile realized value capture with the baseline.
- **Data drift:** monitor recency, order frequency, margin, return, and acquisition-channel distributions.
- **Policy drift:** review tier capacity and investment caps separately from model retraining.
- **Selection effects:** treatment changes future observations; use experiments to measure intervention impact.

Before deployment, rebuild contribution margin definitions, exclude prohibited variables, test performance across relevant operational groups, calibrate uncertainty, document review rights, and establish a retraining threshold.

## Public validation companion

This is an external check of the analytical method, not a production validation of the
synthetic policy.

| Item | Public companion |
|---|---|
| Data | UCI Online Retail II, CC BY 4.0 |
| Unit | Customer at a temporal snapshot |
| Target | Signed net revenue over the next 180 days |
| Test | Untouched 2011-06-01 snapshot, 4,933 customers |
| Safe decision use | Relative ranking and fixed-capacity review evidence |
| Not supported | Profit, spend ceilings, causal treatment choice, production accuracy |

| Public holdout metric | Model | Baseline |
|---|---:|---:|
| WAPE | 0.672 | **0.653** |
| MAE | 554.36 | **538.68** |
| RMSE | 2,835.95 | **2,733.99** |
| Spearman | **0.611** | 0.546 |
| Top 10% value capture | **62.7%** | 60.9% |
| Top 20% value capture | **75.8%** | 73.1% |

The model does not beat the fixed baseline on point error. It is retained because model
selection was completed before the final test and because it provides stronger ranking
evidence; the negative result remains visible. Paired-bootstrap 95% intervals are
+0.5 to +3.0 percentage points for top-10 capture and +1.3 to +4.3 points for top-20
capture. Raw and calibrated interval coverage are both 80.1%, with a £0 conformal
correction because the calibration snapshot already exceeded the nominal target.
Highest-decile coverage is 65.8%, and aggregate predicted value is only 64.5% of
aggregate realized value.

Public raw data, canonical transactions, snapshots, and customer-level scores remain
gitignored. Aggregate evidence is in
[`reports/public_validation/`](../reports/public_validation/).
