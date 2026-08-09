"""Committed reports and figures generated from the untouched holdout."""

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
    "coral": "#E76F51",
    "gray": "#64748B",
    "light": "#E2E8F0",
}


def _style_axis(axis: plt.Axes) -> None:
    axis.spines[["top", "right"]].set_visible(False)
    axis.grid(axis="y", color=COLORS["light"], linewidth=0.8, alpha=0.8)
    axis.set_axisbelow(True)


def _save_figure(figure: plt.Figure, path: Path) -> None:
    figure.tight_layout()
    figure.savefig(path, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(figure)


def plot_value_by_decile(scored: pd.DataFrame, path: Path) -> None:
    """Compare average predicted and realized margin by score decile."""
    chart = scored.copy()
    chart["value_decile"] = pd.qcut(
        chart["predicted_clv_180d"].rank(method="first"),
        10,
        labels=range(1, 11),
    )
    summary = (
        chart.groupby("value_decile", observed=True)
        .agg(
            predicted=("predicted_clv_180d", "mean"),
            realized=("future_discounted_margin_180d", "mean"),
        )
        .reset_index()
    )
    positions = np.arange(len(summary))
    width = 0.38
    figure, axis = plt.subplots(figsize=(9.2, 4.8))
    axis.bar(
        positions - width / 2,
        summary["predicted"],
        width,
        label="Predicted",
        color=COLORS["blue"],
    )
    axis.bar(
        positions + width / 2,
        summary["realized"],
        width,
        label="Realized holdout",
        color=COLORS["teal"],
    )
    axis.set_xticks(positions, [str(value) for value in summary["value_decile"]])
    axis.set_xlabel("Predicted value decile (1 = lowest)")
    axis.set_ylabel("Average 180-day discounted margin")
    axis.set_title("Predicted value separates customers on the untouched period", loc="left")
    axis.legend(frameon=False)
    _style_axis(axis)
    _save_figure(figure, path)


def plot_cumulative_capture(scored: pd.DataFrame, path: Path) -> None:
    """Plot realized value captured as customer coverage increases."""
    actual_total = scored["future_discounted_margin_180d"].sum()
    figure, axis = plt.subplots(figsize=(8.4, 4.8))
    for column, label, color in [
        ("predicted_clv_180d", "CLV model", COLORS["teal"]),
        ("baseline_clv_180d", "RFM value baseline", COLORS["gray"]),
    ]:
        ordered = scored.sort_values(column, ascending=False)
        coverage = np.arange(1, len(ordered) + 1) / len(ordered)
        captured = ordered["future_discounted_margin_180d"].cumsum() / actual_total
        axis.plot(coverage, captured, label=label, color=color, linewidth=2.4)
    axis.plot([0, 1], [0, 1], linestyle="--", color=COLORS["light"], label="Random")
    axis.set_xlabel("Share of customers contacted")
    axis.set_ylabel("Share of realized value captured")
    axis.set_title("Value ranking supports capacity-constrained prioritization", loc="left")
    axis.set_xlim(0, 1)
    axis.set_ylim(0, 1.02)
    axis.legend(frameon=False)
    _style_axis(axis)
    _save_figure(figure, path)


def plot_tier_portfolio(summary: pd.DataFrame, path: Path) -> None:
    """Show the relationship between customer share and realized value share."""
    figure, axis = plt.subplots(figsize=(8.6, 4.8))
    positions = np.arange(len(summary))
    width = 0.36
    axis.bar(
        positions - width / 2,
        summary["customer_share"] * 100,
        width,
        label="Customer share",
        color=COLORS["light"],
    )
    axis.bar(
        positions + width / 2,
        summary["realized_value_share"] * 100,
        width,
        label="Realized value share",
        color=COLORS["gold"],
    )
    tier_labels = [value.replace("_", " ").title() for value in summary["service_tier"]]
    axis.set_xticks(positions, tier_labels)
    axis.set_ylabel("Share (%)")
    axis.set_title("Decision tiers concentrate realized customer value", loc="left")
    axis.legend(frameon=False)
    _style_axis(axis)
    _save_figure(figure, path)


def plot_feature_importance(importance: pd.DataFrame, path: Path) -> None:
    """Plot the ten largest holdout permutation importance values."""
    chart = importance.head(10).sort_values("wape_increase")
    figure, axis = plt.subplots(figsize=(8.6, 5.2))
    axis.barh(
        chart["feature"].str.replace("_", " "),
        chart["wape_increase"],
        color=COLORS["blue"],
    )
    axis.set_xlabel("Increase in holdout WAPE after permutation")
    axis.set_title("Features supporting the CLV estimate", loc="left")
    _style_axis(axis)
    _save_figure(figure, path)


def write_metrics(metrics: dict[str, Any], path: Path) -> None:
    """Write machine-readable results with stable formatting."""
    path.write_text(json.dumps(metrics, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_executive_summary(
    metrics: dict[str, Any],
    policy_summary: pd.DataFrame,
    path: Path,
) -> None:
    """Write a concise business-facing report grounded in executed metrics."""
    model = metrics["holdout"]["model"]
    baseline = metrics["holdout"]["baseline"]
    protect = policy_summary.loc[policy_summary["service_tier"] == "protect"].iloc[0]
    improvement = 1 - model["wape"] / baseline["wape"]
    lines = [
        "# CLV decision report",
        "",
        "## Decision",
        "",
        "Prioritize customers by expected discounted contribution margin over the next "
        "180 days, then translate the ranking into transparent service tiers and "
        "conservative investment ceilings.",
        "",
        "## Untouched holdout evidence",
        "",
        f"- Model WAPE: **{model['wape']:.3f}**, versus **{baseline['wape']:.3f}** "
        f"for the recency-adjusted trailing-margin baseline ({improvement:.1%} relative "
        "error reduction).",
        f"- Spearman rank correlation: **{model['spearman']:.3f}**, versus "
        f"**{baseline['spearman']:.3f}** for the baseline.",
        f"- Top 10% realized value capture: **{model['top_10_value_capture']:.1%}**.",
        "- Empirical coverage of the nominal 80% interval: "
        f"**{model['interval_80_coverage']:.1%}**.",
        f"- The Protect tier contains **{protect['customer_share']:.1%}** of customers "
        f"and **{protect['realized_value_share']:.1%}** of realized holdout value.",
        "",
        "## How to use the output",
        "",
        "The score supports relative prioritization and service-level budgeting. "
        "`investment_ceiling` is a policy guardrail based on the lower prediction bound "
        "and a configurable value fraction. It is not an estimate of treatment uplift "
        "or causal ROI.",
        "",
        "## Limitations",
        "",
        "- All customers and orders are synthetic; the results validate the workflow, "
        "not production performance.",
        "- The model estimates 180-day value, not an unlimited customer lifetime.",
        "- Prediction intervals are empirical model outputs and may require "
        "recalibration after a distribution shift.",
        "- Treatment impact needs randomized experimentation or credible causal "
        "identification; CLV alone cannot supply it.",
        "",
    ]
    content = "\n".join(lines)
    path.write_text(content, encoding="utf-8")


def create_reports(
    scored: pd.DataFrame,
    tier_summary: pd.DataFrame,
    importance: pd.DataFrame,
    metrics: dict[str, Any],
    reports_directory: Path,
) -> None:
    """Create all committed figures and reports."""
    figures = reports_directory / "figures"
    figures.mkdir(parents=True, exist_ok=True)
    write_metrics(metrics, reports_directory / "metrics.json")
    write_executive_summary(metrics, tier_summary, reports_directory / "executive_summary.md")
    plot_value_by_decile(scored, figures / "value_by_decile.png")
    plot_cumulative_capture(scored, figures / "cumulative_value_capture.png")
    plot_tier_portfolio(tier_summary, figures / "tier_portfolio.png")
    plot_feature_importance(importance, figures / "feature_importance.png")
