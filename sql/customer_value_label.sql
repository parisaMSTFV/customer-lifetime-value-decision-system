SELECT
    c.customer_id,
    :snapshot_date AS snapshot_date,
    COUNT(DISTINCT o.order_id) AS future_orders_180d,
    COALESCE(SUM(
        o.contribution_margin /
        (1.0 + :annual_discount_rate *
            (julianday(o.order_date) - julianday(:snapshot_date)) / 365.0)
    ), 0) AS future_discounted_margin_180d
FROM customers AS c
LEFT JOIN orders AS o
  ON c.customer_id = o.customer_id
 AND o.order_date > :snapshot_date
 AND o.order_date <= date(:snapshot_date, '+' || :horizon_days || ' days')
WHERE c.acquisition_date <= :snapshot_date
GROUP BY c.customer_id
ORDER BY c.customer_id;
