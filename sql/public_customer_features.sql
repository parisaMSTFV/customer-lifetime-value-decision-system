WITH parameters AS (
    SELECT
        snapshot_date,
        lookback_days
    FROM snapshot_parameters
),
eligible_customers AS (
    SELECT
        transactions.customer_id,
        MIN(transactions.invoice_date) FILTER (
            WHERE NOT transactions.is_cancellation AND transactions.signed_revenue > 0
        ) AS first_purchase_date,
        ARG_MAX(transactions.country, transactions.invoice_date) AS country
    FROM public_transactions AS transactions
    CROSS JOIN parameters
    WHERE transactions.invoice_date < parameters.snapshot_date
    GROUP BY transactions.customer_id
    HAVING first_purchase_date IS NOT NULL
),
history AS (
    SELECT
        transactions.*,
        DATE_DIFF(
            'day',
            CAST(transactions.invoice_date AS DATE),
            CAST(parameters.snapshot_date AS DATE)
        ) AS age_days
    FROM public_transactions AS transactions
    CROSS JOIN parameters
    WHERE transactions.invoice_date < parameters.snapshot_date
      AND transactions.invoice_date >= parameters.snapshot_date - parameters.lookback_days * INTERVAL 1 DAY
),
aggregates AS (
    SELECT
        customers.customer_id,
        CAST(parameters.snapshot_date AS DATE) AS snapshot_date,
        customers.country,
        DATE_DIFF(
            'day',
            CAST(customers.first_purchase_date AS DATE),
            CAST(parameters.snapshot_date AS DATE)
        ) AS observed_tenure_days,
        COALESCE(
            MIN(history.age_days) FILTER (
                WHERE NOT history.is_cancellation AND history.signed_revenue > 0
            ),
            parameters.lookback_days + 1
        ) AS recency_days,
        COUNT(DISTINCT history.invoice_id) FILTER (
            WHERE NOT history.is_cancellation AND history.signed_revenue > 0 AND history.age_days <= 30
        ) AS orders_30d,
        COUNT(DISTINCT history.invoice_id) FILTER (
            WHERE NOT history.is_cancellation AND history.signed_revenue > 0 AND history.age_days <= 90
        ) AS orders_90d,
        COUNT(DISTINCT history.invoice_id) FILTER (
            WHERE NOT history.is_cancellation AND history.signed_revenue > 0 AND history.age_days <= 180
        ) AS orders_180d,
        COUNT(DISTINCT history.invoice_id) FILTER (
            WHERE NOT history.is_cancellation AND history.signed_revenue > 0 AND history.age_days <= 365
        ) AS orders_365d,
        COALESCE(SUM(history.signed_revenue) FILTER (WHERE history.age_days <= 90), 0) AS net_revenue_90d,
        COALESCE(SUM(history.signed_revenue) FILTER (WHERE history.age_days > 90 AND history.age_days <= 180), 0) AS net_revenue_previous_90d,
        COALESCE(SUM(history.signed_revenue) FILTER (WHERE history.age_days <= 180), 0) AS net_revenue_180d,
        COALESCE(SUM(history.signed_revenue) FILTER (WHERE history.age_days <= 365), 0) AS net_revenue_365d,
        COALESCE(
            COALESCE(SUM(history.signed_revenue) FILTER (WHERE history.age_days <= 365), 0)
            / NULLIF(
                COUNT(DISTINCT history.invoice_id) FILTER (
                    WHERE NOT history.is_cancellation AND history.signed_revenue > 0 AND history.age_days <= 365
                ),
                0
            ),
            0
        ) AS average_order_value_365d,
        COALESCE(
            -SUM(history.signed_revenue) FILTER (
                WHERE history.is_cancellation AND history.age_days <= 365
            )
            / NULLIF(
                SUM(history.signed_revenue) FILTER (
                    WHERE NOT history.is_cancellation AND history.signed_revenue > 0 AND history.age_days <= 365
                ),
                0
            ),
            0
        ) AS return_value_ratio_365d,
        COUNT(DISTINCT history.stock_code) FILTER (
            WHERE NOT history.is_cancellation AND history.signed_revenue > 0 AND history.age_days <= 365
        ) AS product_diversity_365d,
        COUNT(DISTINCT DATE_TRUNC('month', history.invoice_date)) FILTER (
            WHERE NOT history.is_cancellation AND history.signed_revenue > 0 AND history.age_days <= 365
        ) AS active_months_365d
    FROM eligible_customers AS customers
    CROSS JOIN parameters
    LEFT JOIN history ON history.customer_id = customers.customer_id
    GROUP BY
        customers.customer_id,
        customers.country,
        customers.first_purchase_date,
        parameters.snapshot_date,
        parameters.lookback_days
)
SELECT
    *,
    (net_revenue_90d - net_revenue_previous_90d)
        / (ABS(net_revenue_90d) + ABS(net_revenue_previous_90d) + 1.0)
        AS revenue_momentum_90d,
    COALESCE(orders_90d / NULLIF(orders_365d, 0), 0) AS recent_order_share
FROM aggregates;
