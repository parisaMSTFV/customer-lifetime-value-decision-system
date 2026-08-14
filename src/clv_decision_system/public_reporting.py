"""Aggregate-only reports for licensed public CLV validation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

plt.switch_backend("Agg")

COLORS = {
    "navy": "#16324F",
    "blue": "#2F6B8A",
    "teal": "#2A9D8F",
    "gold": "#E9C46A",
    "gray": "#64748B",
    "light": "#E2E8F0",
}


def _finish(axis: plt.Axes) -> None:
    axis.spines[["top", "right"]].set_visible(False)
    axis.grid(axis="y", color=COLORS["light"], linewidth=0.8, alpha=0.8)
    axis.set_axisbelow(True)


def _save(figure: plt.Figure, path: Path) -> None:
    figure.tight_layout()
    figure.savefig(path, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(figure)


def plot_public_deciles(summary: pd.DataFrame, path: Path) -> None:
    """Compare aggregate predicted and realized net revenue by score decile."""
    positions = np.arange(len(summary))
    width = 0.38
    figure, axis = plt.subplots(figsize=(9.2, 4.8))
    axis.bar(
        positions - width / 2,
        summary["average_predicted_revenue"],
        width,
        label="Predicted",
        color=COLORS["blue"],
    )
    axis.bar(
        positions + width / 2,
        summary["average_realized_revenue"],
        width,
        label="Realized",
        color=COLORS["teal"],
    )
    axis.set_xticks(positions, summary["predicted_value_decile"].astype(str))
    axis.set_xlabel("Predicted value decile (1 = lowest)")
    axis.set_ylabel("Average 180-day net revenue (£)")
    axis.set_title("Out-of-time public revenue by predicted-value decile", loc="left")
    axis.legend(frameon=False)
    _finish(axis)
    _save(figure, path)


def plot_public_capture(scored: pd.DataFrame, path: Path) -> None:
    """Plot realized public value captured at each customer coverage level."""
    total = scored["future_net_revenue_180d"].sum()
    figure, axis = plt.subplots(figsize=(8.4, 4.8))
    for column, label, color in [
        ("predicted_revenue_180d", "Two-part model", COLORS["teal"]),
        ("baseline_revenue_180d", "Trailing-value baseline", COLORS["gray"]),
    ]:
        ordered = scored.sort_values(column, ascending=False)
        coverage = np.arange(1, len(ordered) + 1) / len(ordered)
        captured = ordered["future_net_revenue_180d"].cumsum() / total
        axis.plot(coverage, captured, label=label, color=color, linewidth=2.4)
    axis.plot([0, 1], [0, 1], linestyle="--", color=COLORS["light"], label="Random")
    axis.set_xlabel("Share of customers prioritized")
    axis.set_ylabel("Share of realized net revenue captured")
    axis.set_title("External ranking value at fixed customer capacity", loc="left")
    axis.set_xlim(0, 1)
    axis.set_ylim(0, 1.02)
    axis.legend(frameon=False)
    _finish(axis)
    _save(figure, path)


def plot_public_intervals(by_decile: pd.DataFrame, target: float, path: Path) -> None:
    """Show conditional interval coverage without implying subgroup guarantees."""
    positions = np.arange(len(by_decile))
    figure, axis = plt.subplots(figsize=(8.8, 4.8))
    axis.plot(
        positions,
        by_decile["raw_coverage"] * 100,
        marker="o",
        color=COLORS["gray"],
        label="Raw quantile interval",
    )
    axis.plot(
        positions,
        by_decile["calibrated_coverage"] * 100,
        marker="o",
        color=COLORS["teal"],
        label="Split-conformal interval",
    )
    axis.axhline(target * 100, linestyle="--", color=COLORS["gold"], label="Nominal target")
    axis.set_xticks(positions, by_decile["predicted_value_decile"].astype(str))
    axis.set_xlabel("Predicted value decile")
    axis.set_ylabel("Empirical coverage (%)")
    axis.set_ylim(0, 102)
    axis.set_title("Public interval coverage remains heterogeneous", loc="left")
    axis.legend(frameon=False)
    _finish(axis)
    _save(figure, path)


def plot_public_importance(importance: pd.DataFrame, path: Path) -> None:
    """Plot public predictive sensitivity for the ten leading features."""
    chart = importance.head(10).sort_values("wape_increase")
    figure, axis = plt.subplots(figsize=(8.6, 5.2))
    axis.barh(
        chart["feature"].str.replace("_", " "),
        chart["wape_increase"],
        color=COLORS["blue"],
    )
    axis.set_xlabel("Increase in holdout WAPE after permutation")
    axis.set_title("Predictive sensitivity on the public holdout", loc="left")
    _finish(axis)
    _save(figure, path)


def write_public_summary(metrics: dict[str, Any], path: Path) -> None:
    """Write an honest, decision-facing summary from executed aggregate metrics."""
    model = metrics["holdout"]["model"]
    baseline = metrics["holdout"]["baseline"]
    interval = metrics["interval_calibration"]
    conditional = metrics["conditional_interval"]
    difference = 1 - model["wape"] / baseline["wape"]
    comparison = (
        f"{abs(difference):.1%} lower" if difference >= 0 else f"{abs(difference):.1%} higher"
    )
    lines = [
        "# Public external-validation report",
        "",
        "## Scope",
        "",
        "This report tests customer-value ranking on licensed UCI Online Retail II "
        "transactions. The target is 180-day net revenue, not contribution margin, "
        "profit, causal uplift, or unlimited lifetime value.",
        "",
        "## Untouched June 2011 snapshot",
        "",
        f"- Model WAPE: **{model['wape']:.3f}**; baseline WAPE: "
        f"**{baseline['wape']:.3f}**. Model error is **{comparison}** than the fixed "
        "trailing-value baseline.",
        f"- Spearman rank correlation: **{model['spearman']:.3f}**; baseline: "
        f"**{baseline['spearman']:.3f}**.",
        f"- Top 10% realized value capture: **{model['top_10_value_capture']:.1%}**; "
        f"baseline: **{baseline['top_10_value_capture']:.1%}**.",
        f"- Top 20% realized value capture: **{model['top_20_value_capture']:.1%}**; "
        f"baseline: **{baseline['top_20_value_capture']:.1%}**.",
        f"- Raw nominal 80% interval coverage: **{model['interval_80_raw_coverage']:.1%}**; "
        f"split-conformal coverage: **{model['interval_80_coverage']:.1%}**.",
        f"- The conformal correction was **£{interval['correction']:.2f}**, fitted on "
        f"**{interval['calibration_rows']:,}** customers before the test snapshot.",
        f"- The highest predicted-value decile covered **"
        f"{conditional['highest_value_decile_coverage']:.1%}**; marginal coverage is not "
        "a subgroup guarantee.",
        "",
        "## Decision interpretation",
        "",
        "Ranking evidence can support a capacity decision such as which customers receive "
        "manual review first. It cannot determine how much to spend on a customer because "
        "the public source has no margin or treatment-cost fields.",
        "",
        "## Limitations",
        "",
        "- The source represents one anonymous UK-based retailer with a mixed retail and "
        "wholesale customer base.",
        "- Revenue is heavy-tailed, and prediction error must be read together with ranking "
        "and capacity metrics.",
        "- Marginal interval calibration does not guarantee equal coverage by value decile, "
        "country, or future period.",
        "- Historical value prediction does not identify a causal CRM treatment effect.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def create_public_reports(
    scored: pd.DataFrame,
    deciles: pd.DataFrame,
    interval_by_decile: pd.DataFrame,
    importance: pd.DataFrame,
    metrics: dict[str, Any],
    output: Path,
) -> None:
    """Write aggregate tables, figures, metrics, and a report with no customer IDs."""
    figures = output / "figures"
    figures.mkdir(parents=True, exist_ok=True)
    output.mkdir(parents=True, exist_ok=True)
    (output / "metrics.json").write_text(
        json.dumps(metrics, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    deciles.to_csv(output / "value_by_decile.csv", index=False)
    interval_by_decile.to_csv(output / "interval_coverage_by_decile.csv", index=False)
    importance.to_csv(output / "feature_importance.csv", index=False)
    write_public_summary(metrics, output / "executive_summary.md")
    plot_public_deciles(deciles, figures / "value_by_decile.png")
    plot_public_capture(scored, figures / "cumulative_value_capture.png")
    plot_public_intervals(
        interval_by_decile,
        float(metrics["interval_calibration"]["target_coverage"]),
        figures / "interval_coverage.png",
    )
    plot_public_importance(importance, figures / "feature_importance.png")
