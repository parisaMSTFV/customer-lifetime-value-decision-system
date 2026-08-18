# Executable SQL layer

The repository executes two independent SQL paths:

- `customer_value_snapshot.sql` and `customer_value_label.sql` build the synthetic
  contribution-margin case study in an in-memory SQLite database.
- `public_transaction_contract.sql`, `public_customer_features.sql`, and
  `public_customer_label.sql` build external-validation snapshots in DuckDB.

## Public-data grains

| Object | Grain | Boundary |
|---|---|---|
| `public_transactions` | One canonical transaction line | Verified and typed before aggregation |
| `public_customer_features` | Customer × scoring date | `invoice_date < snapshot_date` |
| `public_customer_labels` | Customer × scoring date | `snapshot_date <= invoice_date < snapshot_date + 180 days` |

The scoring date is midnight at the start of the named day. Transactions on that day
belong to the future label, never to the feature window. Cancellations remain negative
signed revenue in historical features and the future target. Future activity is a
separate label based on any value-bearing future transaction, so the target is exactly
zero when activity is absent and can be negative when returns exceed purchases.

## Run

```bash
python scripts/download_public_data.py
python scripts/build_public_snapshots.py
```

`tests/test_public_features.py` compares DuckDB results with an intentionally simple
Pandas reference on a hand-checkable fixture. This parity test covers feature windows,
the scoring boundary, returns, future labels, and customer keys.
