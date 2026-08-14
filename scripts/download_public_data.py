"""Download and canonicalize UCI Online Retail II without committing raw records."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from clv_decision_system.public_data import (  # noqa: E402, I001
    DATASET_SHA256,
    download_dataset,
    extract_workbook,
    prepare_public_data,
    sha256_file,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="Download the verified archive again")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    external = PROJECT_ROOT / "data" / "external"
    archive = external / "raw" / "online-retail-ii.zip"
    workbook = external / "raw" / "online_retail_II.xlsx"
    if args.force or not archive.exists() or sha256_file(archive) != DATASET_SHA256:
        download_dataset(archive)
    if args.force or not workbook.exists():
        extract_workbook(archive, workbook)
    quality = prepare_public_data(
        workbook,
        external / "processed" / "transactions.csv.gz",
        external / "quality_report.json",
    )
    print(json.dumps(quality, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
