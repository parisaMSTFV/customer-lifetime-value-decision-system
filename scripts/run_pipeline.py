"""Command-line entry point for the full reproducible pipeline."""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from clv_decision_system.pipeline import run_pipeline  # noqa: E402, I001

if __name__ == "__main__":
    results = run_pipeline(PROJECT_ROOT)
    print(json.dumps(results, indent=2, sort_keys=True))
