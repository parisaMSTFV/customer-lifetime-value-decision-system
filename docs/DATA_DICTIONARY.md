# Data Dictionary

All records are synthetic. Customer IDs and order IDs are generated sequence keys and do not map to any person or business system.

## `data/synthetic/customers.csv`

| Column | Type | Definition |
|---|---|---|
| `customer_id` | string | Synthetic customer key |
| `acquisition_date` | date | Synthetic relationship start date |
| `acquisition_channel` | category | Organic, paid search, affiliate, or referral |
| `region` | category | Broad synthetic operating region |

## `data/synthetic/orders.csv`

| Column | Type | Definition |
|---|---|---|
| `order_id` | string | Synthetic order key |
| `customer_id` | string | Synthetic customer key |
| `order_date` | date | Order date |
| `category` | category | Generic merchandise category |
| `order_channel` | category | App, web, or assisted channel |
| `net_revenue` | float | Revenue after the synthetic discount |
| `contribution_margin` | float | Revenue less synthetic product, fulfillment, and return costs |
| `discount_ratio` | float | Share of gross revenue discounted |
| `returned` | integer | Synthetic return indicator |

## `data/processed/customer_snapshots.csv`

### Keys and context

| Column | Definition |
|---|---|
| `customer_id` | Synthetic customer key |
| `snapshot_date` | As-of date for all feature calculations |
| `acquisition_channel`, `region` | Customer acquisition context |
| `tenure_days` | Days from acquisition to snapshot |

### Behavioral features

| Column family | Definition |
|---|---|
| `recency_days` | Days since the most recent order at the snapshot |
| `orders_*d` | Distinct order count in 30, 90, 180, or 365 days |
| `revenue_*d` | Net revenue in 90, 180, or 365 days |
| `margin_*d` | Contribution margin in recent windows |
| `margin_previous_90d` | Margin from days 91–180 before the snapshot |
| `margin_momentum_90d` | Recent 90-day margin minus previous 90-day margin |
| `average_order_value_365d` | Mean order revenue in the lookback |
| `average_discount_365d` | Mean discount ratio in the lookback |
| `return_rate_365d` | Share of orders returned in the lookback |
| `category_diversity_365d` | Count of distinct categories purchased |
| `active_months_365d` | Months with at least one order |
| `recent_order_share` | 90-day orders divided by 365-day orders |

### Outcomes

| Column | Definition |
|---|---|
| `future_orders_180d` | Order count after the snapshot through day 180 |
| `future_discounted_margin_180d` | Discounted contribution margin in that horizon |
| `future_active_180d` | Indicator for positive future discounted margin |

## `artifacts/holdout_customer_scores.csv`

| Column | Definition |
|---|---|
| `predicted_clv_180d` | Expected 180-day discounted contribution margin |
| `active_probability_180d` | Estimated probability of activity in the horizon |
| `clv_lower_80`, `clv_upper_80` | Nominal 80% model interval |
| `service_tier` | Relative capacity tier |
| `high_uncertainty` | Wide-interval review flag |
| `investment_ceiling` | Policy cap based on lower-bound value and tier configuration |
| `baseline_clv_180d` | Fixed recency-adjusted trailing-margin estimate |
