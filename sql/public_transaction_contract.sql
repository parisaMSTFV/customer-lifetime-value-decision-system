CREATE OR REPLACE TEMP TABLE public_transactions AS
SELECT
    CAST(invoice_id AS VARCHAR) AS invoice_id,
    CAST(stock_code AS VARCHAR) AS stock_code,
    CAST(quantity AS DOUBLE) AS quantity,
    CAST(invoice_date AS TIMESTAMP) AS invoice_date,
    CAST(unit_price AS DOUBLE) AS unit_price,
    CAST(customer_id AS VARCHAR) AS customer_id,
    CAST(country AS VARCHAR) AS country,
    CAST(is_cancellation AS BOOLEAN) AS is_cancellation,
    CAST(signed_revenue AS DOUBLE) AS signed_revenue,
    CAST(source_sheet AS VARCHAR) AS source_sheet
FROM transactions_source;

CREATE INDEX idx_public_customer_date
ON public_transactions(customer_id, invoice_date);
