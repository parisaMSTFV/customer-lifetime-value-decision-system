"""Build ignored leakage-safe public snapshots with DuckDB SQL."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from clv_decision_system.config import load_public_validation_config  # noqa: E402, I001
from clv_decision_system.public_data import read_canonical_transactions  # noqa: E402, I001
from clv_decision_system.public_features import (  # noqa: E402, I001
    build_public_customer_snapshots,
)


def main() -> None:
    config = load_public_validation_config(PROJECT_ROOT / "configs" / "public_validation.json")
    processed = PROJECT_ROOT / "data" / "external" / "processed"
    transactions_path = processed / "transactions.csv.gz"
    if not transactions_path.exists():
        raise FileNotFoundError(
            "Canonical public transactions are missing. Run scripts/download_public_data.py first."
        )
    transactions = read_canonical_transactions(transactions_path)
    snapshots = build_public_customer_snapshots(
        transactions,
        config["snapshot_dates"],
        config["lookback_days"],
        config["horizon_days"],
        PROJECT_ROOT / "sql",
    )
    output = processed / "customer_snapshots.csv.gz"
    snapshots.to_csv(output, index=False, compression="gzip")
    fingerprint = hashlib.sha256(
        pd.util.hash_pandas_object(snapshots, index=True).values.tobytes()
    ).hexdigest()[:16]
    print(
        json.dumps(
            {
                "customers": int(snapshots["customer_id"].nunique()),
                "fingerprint": fingerprint,
                "rows": int(len(snapshots)),
                "snapshot_dates": config["snapshot_dates"],
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
