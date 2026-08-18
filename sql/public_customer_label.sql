WITH parameters AS (
    SELECT
        snapshot_date,
        horizon_days
    FROM snapshot_parameters
),
eligible_customers AS (
    SELECT DISTINCT customer_id
    FROM public_transactions
    CROSS JOIN parameters
    WHERE invoice_date < parameters.snapshot_date
      AND NOT is_cancellation
      AND signed_revenue > 0
),
future_value AS (
    SELECT
        transactions.customer_id,
        SUM(transactions.signed_revenue) AS signed_revenue,
        COUNT(*) AS transaction_lines
    FROM public_transactions AS transactions
    CROSS JOIN parameters
    WHERE transactions.invoice_date >= parameters.snapshot_date
      AND transactions.invoice_date < parameters.snapshot_date + parameters.horizon_days * INTERVAL 1 DAY
    GROUP BY transactions.customer_id
)
SELECT
    customers.customer_id,
    CAST(parameters.snapshot_date AS DATE) AS snapshot_date,
    COALESCE(future_value.signed_revenue, 0) AS future_net_revenue_180d,
    CAST(COALESCE(future_value.transaction_lines, 0) > 0 AS INTEGER) AS future_active_180d
FROM eligible_customers AS customers
CROSS JOIN parameters
LEFT JOIN future_value ON future_value.customer_id = customers.customer_id;
