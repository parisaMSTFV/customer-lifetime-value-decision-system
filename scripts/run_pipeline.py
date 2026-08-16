"""Command-line entry point for the full reproducible pipeline."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from clv_decision_system.pipeline import run_pipeline  # noqa: E402, I001


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the synthetic CLV decision pipeline.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "local-runs" / "latest",
        help="Output root; defaults to an ignored local-run directory.",
    )
    return parser


if __name__ == "__main__":
    args = build_parser().parse_args()
    results = run_pipeline(PROJECT_ROOT, output_dir=args.output_dir)
    print(json.dumps(results, indent=2, sort_keys=True))
