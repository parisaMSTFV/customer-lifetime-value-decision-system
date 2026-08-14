# Public validation data card

## Source and license

- **Dataset:** Online Retail II
- **Publisher:** UCI Machine Learning Repository
- **Creator:** Daqing Chen
- **DOI:** [10.24432/C5CG6D](https://doi.org/10.24432/C5CG6D)
- **Source:** [UCI dataset page](https://archive.ics.uci.edu/dataset/502/online%2Bretail%2Bii)
- **License:** Creative Commons Attribution 4.0 International (CC BY 4.0)
- **Official archive SHA-256:** `572e36277c2390fbfde10664750731e0a86f55e33470d91919085f0408e67bfb`

The UCI page describes 1,067,371 transaction lines from a UK-based non-store retailer
between 1 December 2009 and 9 December 2011. The workbook contains two annual sheets.

## Purpose

This dataset provides an out-of-simulation check of temporal feature construction,
customer-value ranking, interval calibration, and fixed-capacity value capture. It does
not replace the synthetic case study's contribution-margin decision policy.

The public target is **180-day net revenue**, floored at zero per customer and horizon.
The source does not contain cost of goods, fulfillment cost, marketing cost, or
contribution margin. Public results must therefore not be described as profit, causal
incrementality, or complete lifetime value.

## Fields used

| Canonical field | Source field | Use |
|---|---|---|
| `invoice_id` | `Invoice` | Distinct transaction and cancellation identification |
| `stock_code` | `StockCode` | Product-diversity features |
| `quantity` | `Quantity` | Sale or return quantity |
| `invoice_date` | `InvoiceDate` | As-of features and future labels |
| `unit_price` | `Price` | Line revenue |
| `customer_id` | `Customer ID` | Customer-level snapshots |
| `country` | `Country` | Public categorical context |

Product descriptions are not required by the model and are dropped during
canonicalization.

## Quality and exclusion policy

- Rows without a customer identifier cannot support customer-level validation and are
  excluded with counts retained in the local quality report.
- Rows with missing critical identifiers or dates, zero quantity, or nonpositive price
  are excluded.
- Exact duplicate transaction lines are removed before customer aggregation and counted
  in the quality report.
- An invoice beginning with `C` or a negative quantity is treated as a cancellation.
- Cancellation value is retained as negative signed revenue instead of being silently
  discarded.
- Raw and canonical row-level files remain under ignored `data/external/` paths. Only
  aggregate reports are eligible for publication.

## Known limitations

- Customer identifiers are pseudonymous but the retailer and operating context are not
  representative of every ecommerce business.
- The retailer serves both retail and wholesale customers, which can create a heavy
  revenue tail.
- Country is available, but acquisition channel, service exposure, marketing treatment,
  margin, and customer consent attributes are absent.
- Historical transactions cannot establish that a proposed CRM action will change
  customer behavior.

## Citation

Chen, D. (2012). *Online Retail II* [Dataset]. UCI Machine Learning Repository.
https://doi.org/10.24432/C5CG6D
