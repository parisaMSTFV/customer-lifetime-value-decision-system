"""Run the licensed public-data model and write aggregate-only reports."""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from clv_decision_system.public_pipeline import run_public_validation  # noqa: E402, I001

if __name__ == "__main__":
    results = run_public_validation(PROJECT_ROOT)
    print(json.dumps(results, indent=2, sort_keys=True))
