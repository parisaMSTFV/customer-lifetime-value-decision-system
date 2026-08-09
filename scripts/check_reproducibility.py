"""Validate generated machine-readable outputs with strict numeric tolerance."""

from __future__ import annotations

import io
import json
import math
import subprocess
from numbers import Real
from pathlib import Path
from typing import Any

import pandas as pd

CSV_PATHS = (
    Path("artifacts/feature_importance.csv"),
    Path("artifacts/holdout_customer_scores.csv"),
    Path("artifacts/service_tier_summary.csv"),
)
JSON_PATHS = (
    Path("artifacts/model_metadata.json"),
    Path("reports/metrics.json"),
)
TEXT_PATHS = (Path("reports/executive_summary.md"),)
REL_TOLERANCE = 1e-12
ABS_TOLERANCE = 1e-12


def committed_bytes(path: Path) -> bytes:
    """Read the committed version without modifying the working tree."""
    result = subprocess.run(
        ["git", "show", f"HEAD:{path.as_posix()}"],
        check=True,
        capture_output=True,
    )
    return result.stdout


def compare_values(expected: Any, actual: Any, location: str) -> None:
    """Recursively compare JSON values while tolerating machine-level float noise."""
    if isinstance(expected, dict) and isinstance(actual, dict):
        if expected.keys() != actual.keys():
            raise AssertionError(f"{location}: JSON keys differ")
        for key in expected:
            compare_values(expected[key], actual[key], f"{location}.{key}")
        return

    if isinstance(expected, list) and isinstance(actual, list):
        if len(expected) != len(actual):
            raise AssertionError(f"{location}: list lengths differ")
        for index, (expected_item, actual_item) in enumerate(zip(expected, actual, strict=True)):
            compare_values(expected_item, actual_item, f"{location}[{index}]")
        return

    numeric_pair = (
        isinstance(expected, Real)
        and not isinstance(expected, bool)
        and isinstance(actual, Real)
        and not isinstance(actual, bool)
    )
    if numeric_pair:
        if not math.isclose(
            float(expected),
            float(actual),
            rel_tol=REL_TOLERANCE,
            abs_tol=ABS_TOLERANCE,
        ):
            raise AssertionError(f"{location}: {expected!r} != {actual!r}")
        return

    if expected != actual:
        raise AssertionError(f"{location}: {expected!r} != {actual!r}")


def compare_csv(path: Path) -> None:
    expected = pd.read_csv(io.BytesIO(committed_bytes(path)))
    actual = pd.read_csv(path)
    pd.testing.assert_frame_equal(
        expected,
        actual,
        check_exact=False,
        rtol=REL_TOLERANCE,
        atol=ABS_TOLERANCE,
        obj=path.as_posix(),
    )


def compare_json(path: Path) -> None:
    expected = json.loads(committed_bytes(path))
    actual = json.loads(path.read_text(encoding="utf-8"))
    compare_values(expected, actual, path.as_posix())


def compare_text(path: Path) -> None:
    expected = committed_bytes(path).decode("utf-8")
    actual = path.read_text(encoding="utf-8")
    if expected != actual:
        raise AssertionError(f"{path}: generated text differs from the committed version")


def main() -> None:
    for path in CSV_PATHS:
        compare_csv(path)
    for path in JSON_PATHS:
        compare_json(path)
    for path in TEXT_PATHS:
        compare_text(path)
    print("Generated machine-readable outputs are reproducible within tolerance.")


if __name__ == "__main__":
    main()
