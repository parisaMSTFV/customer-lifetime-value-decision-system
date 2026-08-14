"""Download and canonicalize the licensed UCI Online Retail II dataset."""

from __future__ import annotations

import hashlib
import json
import shutil
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

DATASET_URL = "https://archive.ics.uci.edu/static/public/502/online%2Bretail%2Bii.zip"
DATASET_SHA256 = "572e36277c2390fbfde10664750731e0a86f55e33470d91919085f0408e67bfb"
WORKBOOK_MEMBER = "online_retail_II.xlsx"
SOURCE_COLUMNS = {
    "Invoice",
    "StockCode",
    "Quantity",
    "InvoiceDate",
    "Price",
    "Customer ID",
    "Country",
    "source_sheet",
}
CANONICAL_COLUMNS = [
    "invoice_id",
    "stock_code",
    "quantity",
    "invoice_date",
    "unit_price",
    "customer_id",
    "country",
    "is_cancellation",
    "signed_revenue",
    "source_sheet",
]


def sha256_file(path: str | Path) -> str:
    """Return a streaming SHA-256 digest for a local file."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_dataset(
    destination: str | Path,
    url: str = DATASET_URL,
    expected_sha256: str = DATASET_SHA256,
) -> Path:
    """Download the source archive and reject incomplete or changed content."""
    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_suffix(f"{target.suffix}.part")
    request = urllib.request.Request(url, headers={"User-Agent": "clv-public-validation/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=120) as response, partial.open("wb") as output:
            shutil.copyfileobj(response, output, length=1024 * 1024)
        observed = sha256_file(partial)
        if observed != expected_sha256:
            raise ValueError(
                f"Downloaded dataset checksum differs from the documented UCI archive: {observed}"
            )
        partial.replace(target)
    finally:
        partial.unlink(missing_ok=True)
    return target


def extract_workbook(archive_path: str | Path, destination: str | Path) -> Path:
    """Extract only the expected workbook member from the verified source archive."""
    archive = Path(archive_path)
    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as bundle:
        members = bundle.namelist()
        if WORKBOOK_MEMBER not in members:
            raise ValueError(f"Archive does not contain {WORKBOOK_MEMBER!r}: {members}")
        with bundle.open(WORKBOOK_MEMBER) as source, target.open("wb") as output:
            shutil.copyfileobj(source, output)
    return target


def _source_quality_counts(frame: pd.DataFrame) -> dict[str, int]:
    numeric_price = pd.to_numeric(frame.get("Price"), errors="coerce")
    numeric_quantity = pd.to_numeric(frame.get("Quantity"), errors="coerce")
    return {
        "source_rows": int(len(frame)),
        "missing_customer_rows": int(frame.get("Customer ID").isna().sum()),
        "missing_invoice_date_rows": int(
            pd.to_datetime(frame.get("InvoiceDate"), errors="coerce").isna().sum()
        ),
        "nonpositive_price_rows": int((numeric_price.fillna(0) <= 0).sum()),
        "zero_quantity_rows": int((numeric_quantity.fillna(0) == 0).sum()),
        "exact_duplicate_rows": int(frame.duplicated().sum()),
    }


def canonicalize_transactions(frame: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int]]:
    """Create a typed, customer-addressable transaction table for validation."""
    missing = SOURCE_COLUMNS.difference(frame.columns)
    if missing:
        raise ValueError(f"Public dataset is missing required columns: {sorted(missing)}")

    quality = _source_quality_counts(frame)
    canonical = frame.rename(
        columns={
            "Invoice": "invoice_id",
            "StockCode": "stock_code",
            "Quantity": "quantity",
            "InvoiceDate": "invoice_date",
            "Price": "unit_price",
            "Customer ID": "customer_id",
            "Country": "country",
        }
    ).copy()
    canonical["invoice_id"] = canonical["invoice_id"].astype("string").str.strip()
    canonical["stock_code"] = canonical["stock_code"].astype("string").str.strip()
    canonical["quantity"] = pd.to_numeric(canonical["quantity"], errors="coerce")
    canonical["invoice_date"] = pd.to_datetime(canonical["invoice_date"], errors="coerce")
    canonical["unit_price"] = pd.to_numeric(canonical["unit_price"], errors="coerce")
    canonical["customer_id"] = pd.to_numeric(canonical["customer_id"], errors="coerce")
    canonical["country"] = canonical["country"].astype("string").str.strip()
    canonical["source_sheet"] = canonical["source_sheet"].astype("string")

    valid = (
        canonical["invoice_id"].notna()
        & canonical["stock_code"].notna()
        & canonical["invoice_date"].notna()
        & canonical["customer_id"].notna()
        & canonical["country"].notna()
        & canonical["quantity"].notna()
        & canonical["unit_price"].notna()
        & canonical["quantity"].ne(0)
        & canonical["unit_price"].gt(0)
    )
    canonical = canonical.loc[valid].copy()
    non_integer_customer = ~np.isclose(
        canonical["customer_id"], canonical["customer_id"].round(), equal_nan=False
    )
    if non_integer_customer.any():
        raise ValueError("Customer identifiers contain non-integer numeric values")
    canonical["customer_id"] = canonical["customer_id"].round().astype("int64").astype("string")
    canonical["is_cancellation"] = canonical["invoice_id"].str.upper().str.startswith(
        "C"
    ) | canonical["quantity"].lt(0)
    absolute_value = canonical["quantity"].abs() * canonical["unit_price"]
    canonical["signed_revenue"] = np.where(
        canonical["is_cancellation"], -absolute_value, absolute_value
    )
    canonical = (
        canonical[CANONICAL_COLUMNS]
        .drop_duplicates()
        .sort_values(["invoice_date", "invoice_id", "stock_code"], kind="stable")
    )
    canonical = canonical.reset_index(drop=True)
    quality.update(
        {
            "usable_rows": int(len(canonical)),
            "excluded_rows": int(quality["source_rows"] - len(canonical)),
            "cancellation_rows": int(canonical["is_cancellation"].sum()),
            "customers": int(canonical["customer_id"].nunique()),
            "invoices": int(canonical["invoice_id"].nunique()),
        }
    )
    return canonical, quality


def load_online_retail_ii(workbook_path: str | Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Load both official workbook sheets and return canonical rows plus audit counts."""
    sheets = pd.read_excel(Path(workbook_path), sheet_name=None)
    if not sheets:
        raise ValueError("Public workbook contains no sheets")
    frames: list[pd.DataFrame] = []
    per_sheet: dict[str, int] = {}
    for sheet_name, frame in sheets.items():
        current = frame.copy()
        current["source_sheet"] = sheet_name
        frames.append(current)
        per_sheet[sheet_name] = int(len(current))
    canonical, quality = canonicalize_transactions(pd.concat(frames, ignore_index=True))
    quality_report: dict[str, Any] = {
        **quality,
        "source_sheets": per_sheet,
        "date_min": canonical["invoice_date"].min().isoformat(),
        "date_max": canonical["invoice_date"].max().isoformat(),
        "countries": int(canonical["country"].nunique()),
    }
    return canonical, quality_report


def prepare_public_data(
    workbook_path: str | Path,
    processed_path: str | Path,
    quality_path: str | Path,
) -> dict[str, Any]:
    """Write the ignored canonical table and its ignored local quality report."""
    canonical, quality = load_online_retail_ii(workbook_path)
    processed = Path(processed_path)
    processed.parent.mkdir(parents=True, exist_ok=True)
    canonical.to_csv(processed, index=False, compression="gzip", date_format="%Y-%m-%d %H:%M:%S")
    report = Path(quality_path)
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(quality, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return quality


def read_canonical_transactions(path: str | Path) -> pd.DataFrame:
    """Read the ignored canonical table with stable identifier and date types."""
    frame = pd.read_csv(
        Path(path),
        compression="gzip",
        dtype={
            "invoice_id": "string",
            "stock_code": "string",
            "customer_id": "string",
            "country": "string",
            "source_sheet": "string",
        },
        parse_dates=["invoice_date"],
    )
    missing = set(CANONICAL_COLUMNS).difference(frame.columns)
    if missing:
        raise ValueError(f"Canonical public table is missing columns: {sorted(missing)}")
    if frame.empty:
        raise ValueError("Canonical public table is empty")
    return frame[CANONICAL_COLUMNS]
