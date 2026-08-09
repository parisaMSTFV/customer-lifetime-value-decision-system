WITH order_features AS (
    SELECT
        customer_id,
        MAX(order_date) AS last_order_date,
        COUNT(DISTINCT order_id) AS orders_365d,
        COUNT(DISTINCT CASE
            WHEN order_date > date(:snapshot_date, '-30 days') THEN order_id
        END) AS orders_30d,
        COUNT(DISTINCT CASE
            WHEN order_date > date(:snapshot_date, '-90 days') THEN order_id
        END) AS orders_90d,
        COUNT(DISTINCT CASE
            WHEN order_date > date(:snapshot_date, '-180 days') THEN order_id
        END) AS orders_180d,
        SUM(net_revenue) AS revenue_365d,
        SUM(CASE
            WHEN order_date > date(:snapshot_date, '-90 days') THEN net_revenue ELSE 0
        END) AS revenue_90d,
        SUM(CASE
            WHEN order_date > date(:snapshot_date, '-180 days') THEN net_revenue ELSE 0
        END) AS revenue_180d,
        SUM(contribution_margin) AS margin_365d,
        SUM(CASE
            WHEN order_date > date(:snapshot_date, '-90 days') THEN contribution_margin ELSE 0
        END) AS margin_90d,
        SUM(CASE
            WHEN order_date > date(:snapshot_date, '-180 days') THEN contribution_margin ELSE 0
        END) AS margin_180d,
        SUM(CASE
            WHEN order_date <= date(:snapshot_date, '-90 days')
             AND order_date > date(:snapshot_date, '-180 days')
            THEN contribution_margin ELSE 0
        END) AS margin_previous_90d,
        AVG(net_revenue) AS average_order_value_365d,
        AVG(discount_ratio) AS average_discount_365d,
        AVG(returned) AS return_rate_365d,
        COUNT(DISTINCT category) AS category_diversity_365d,
        COUNT(DISTINCT strftime('%Y-%m', order_date)) AS active_months_365d
    FROM orders
    WHERE order_date <= :snapshot_date
      AND order_date > date(:snapshot_date, '-' || :lookback_days || ' days')
    GROUP BY customer_id
)
SELECT
    c.customer_id,
    :snapshot_date AS snapshot_date,
    c.acquisition_channel,
    c.region,
    CAST(julianday(:snapshot_date) - julianday(c.acquisition_date) AS INTEGER) AS tenure_days,
    COALESCE(
        CAST(julianday(:snapshot_date) - julianday(f.last_order_date) AS INTEGER),
        :lookback_days + 1
    ) AS recency_days,
    COALESCE(f.orders_30d, 0) AS orders_30d,
    COALESCE(f.orders_90d, 0) AS orders_90d,
    COALESCE(f.orders_180d, 0) AS orders_180d,
    COALESCE(f.orders_365d, 0) AS orders_365d,
    COALESCE(f.revenue_90d, 0) AS revenue_90d,
    COALESCE(f.revenue_180d, 0) AS revenue_180d,
    COALESCE(f.revenue_365d, 0) AS revenue_365d,
    COALESCE(f.margin_90d, 0) AS margin_90d,
    COALESCE(f.margin_previous_90d, 0) AS margin_previous_90d,
    COALESCE(f.margin_180d, 0) AS margin_180d,
    COALESCE(f.margin_365d, 0) AS margin_365d,
    COALESCE(f.average_order_value_365d, 0) AS average_order_value_365d,
    COALESCE(f.average_discount_365d, 0) AS average_discount_365d,
    COALESCE(f.return_rate_365d, 0) AS return_rate_365d,
    COALESCE(f.category_diversity_365d, 0) AS category_diversity_365d,
    COALESCE(f.active_months_365d, 0) AS active_months_365d,
    COALESCE(f.margin_90d, 0) - COALESCE(f.margin_previous_90d, 0) AS margin_momentum_90d,
    CASE
        WHEN COALESCE(f.orders_365d, 0) = 0 THEN 0
        ELSE 1.0 * COALESCE(f.orders_90d, 0) / COALESCE(f.orders_365d, 0)
    END AS recent_order_share
FROM customers AS c
LEFT JOIN order_features AS f
  ON c.customer_id = f.customer_id
WHERE c.acquisition_date <= :snapshot_date
ORDER BY c.customer_id;

