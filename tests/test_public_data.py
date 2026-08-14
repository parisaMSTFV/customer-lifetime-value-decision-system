"""Tests for licensed public-data ingestion and canonicalization."""

from __future__ import annotations

import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from clv_decision_system.public_data import (  # noqa: E402, I001
    WORKBOOK_MEMBER,
    canonicalize_transactions,
    extract_workbook,
    load_online_retail_ii,
    sha256_file,
)


def source_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Invoice": ["100", "C101", "102", "103", "104"],
            "StockCode": ["A", "A", "B", "C", "D"],
            "Description": ["One", "One", "Two", "Three", "Four"],
            "Quantity": [2, -1, 3, 1, 1],
            "InvoiceDate": pd.to_datetime(
                ["2010-01-01", "2010-01-02", "2010-01-03", "2010-01-04", "2010-01-05"]
            ),
            "Price": [5.0, 5.0, 4.0, 3.0, 0.0],
            "Customer ID": [1.0, 1.0, 2.0, None, 3.0],
            "Country": ["United Kingdom", "United Kingdom", "France", "France", "Germany"],
            "source_sheet": ["fixture"] * 5,
        }
    )


class PublicDataTests(unittest.TestCase):
    def test_canonicalization_keeps_returns_as_negative_revenue(self) -> None:
        canonical, quality = canonicalize_transactions(source_frame())
        self.assertEqual(len(canonical), 3)
        self.assertEqual(quality["missing_customer_rows"], 1)
        self.assertEqual(quality["nonpositive_price_rows"], 1)
        cancellation = canonical.loc[canonical["invoice_id"] == "C101"].iloc[0]
        self.assertTrue(cancellation["is_cancellation"])
        self.assertEqual(cancellation["signed_revenue"], -5.0)
        self.assertEqual(set(canonical["customer_id"]), {"1", "2"})

    def test_missing_source_column_fails_fast(self) -> None:
        with self.assertRaisesRegex(ValueError, "missing required columns"):
            canonicalize_transactions(source_frame().drop(columns="Price"))

    def test_exact_duplicate_transaction_lines_are_removed(self) -> None:
        frame = source_frame()
        frame = pd.concat([frame, frame.iloc[[0]]], ignore_index=True)
        canonical, quality = canonicalize_transactions(frame)
        self.assertEqual(len(canonical), 3)
        self.assertEqual(quality["exact_duplicate_rows"], 1)

    def test_verified_member_is_extracted_without_directory_expansion(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / "source.zip"
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr(WORKBOOK_MEMBER, b"workbook-bytes")
                bundle.writestr("ignored.txt", b"not extracted")
            target = extract_workbook(archive, root / "output.xlsx")
            self.assertEqual(target.read_bytes(), b"workbook-bytes")
            self.assertFalse((root / "ignored.txt").exists())
            self.assertEqual(sha256_file(target), sha256_file(target))

    def test_loader_combines_both_workbook_sheets(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workbook = Path(temporary) / "fixture.xlsx"
            frame = source_frame().drop(columns="source_sheet")
            with pd.ExcelWriter(workbook) as writer:
                frame.iloc[:2].to_excel(writer, sheet_name="Year 1", index=False)
                frame.iloc[2:].to_excel(writer, sheet_name="Year 2", index=False)
            canonical, quality = load_online_retail_ii(workbook)
            self.assertEqual(len(canonical), 3)
            self.assertEqual(quality["source_rows"], 5)
            self.assertEqual(quality["source_sheets"], {"Year 1": 2, "Year 2": 3})
            self.assertEqual(quality["countries"], 2)


if __name__ == "__main__":
    unittest.main()
