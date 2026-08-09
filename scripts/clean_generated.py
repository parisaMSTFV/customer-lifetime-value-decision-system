"""Remove only known generated output directories."""

from __future__ import annotations

import shutil
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
GENERATED_PATHS = [
    PROJECT_ROOT / "artifacts",
    PROJECT_ROOT / "reports",
    PROJECT_ROOT / "data" / "processed",
    PROJECT_ROOT / "data" / "synthetic",
]


if __name__ == "__main__":
    for path in GENERATED_PATHS:
        if path.exists() and path.is_dir() and PROJECT_ROOT in path.parents:
            shutil.rmtree(path)
            print(f"Removed {path.relative_to(PROJECT_ROOT)}")
