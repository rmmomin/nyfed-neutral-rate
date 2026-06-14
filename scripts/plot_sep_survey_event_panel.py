#!/usr/bin/env python3
"""
Plot event-level SEP and NY Fed survey predictiveness windows side by side.

Reads:
  - data_out/nyfed_future_sep_predictive_event_analysis.csv
  - data_out/sep_future_nyfed_predictive_event_analysis.csv

Outputs:
  - data_out/sep_survey_event_panel.png
"""

import argparse
import sys
from pathlib import Path
from typing import Tuple

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.chart_style import add_chart_footer


PANEL_ORDER = ["SPD", "SMP", "Combined"]
PANEL_LABELS = {
    "SPD": "NY Fed SPD",
    "SMP": "NY Fed SMP",
    "Combined": "NY Fed Combined",
}
PANEL_COLORS = {
    "SPD": "#1a5f7a",
    "SMP": "#2a9d8f",
    "Combined": "#f4a261",
}
PANEL_MARKERS = {
    "SPD": "o",
    "SMP": "v",
    "Combined": "s",
}


def ols(y: pd.Series, x: pd.Series) -> Tuple[float, float, float]:
    data = pd.concat([y.rename("y"), x.rename("x")], axis=1).dropna()
    if data.empty:
        return np.nan, np.nan, np.nan

    y_values = data["y"].astype(float).to_numpy()
    x_values = data["x"].astype(float).to_numpy()
    design = np.column_stack([np.ones(len(x_values)), x_values])
    intercept, slope = np.linalg.lstsq(design, y_values, rcond=None)[0]
    fitted = design @ np.array([intercept, slope])
    residual_ss = np.square(y_values - fitted).sum()
    total_ss = np.square(y_values - y_values.mean()).sum()
    r_squared = 1 - residual_ss / total_ss if total_ss else np.nan
    return intercept, slope, r_squared


def axis_limits(*series: pd.Series) -> Tuple[float, float]:
    values = pd.concat(series).dropna().astype(float)
    if values.empty:
        return -1, 1

    low = np.floor(values.min() / 10) * 10
    high = np.ceil(values.max() / 10) * 10
    pad = 5
    return low - pad, high + pad


def draw_event_panel(
    ax,
    data: pd.DataFrame,
    x_col: str,
    y_col: str,
    title: str,
    x_label: str,
    y_label: str,
) -> None:
    ax.set_facecolor("white")
    ax.grid(True, alpha=0.3, linestyle="-", linewidth=0.5)
    ax.set_axisbelow(True)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.axhline(0, color="#333333", linewidth=1.0)
    ax.axvline(0, color="#333333", linewidth=1.0)

    for panel_name in PANEL_ORDER:
        group = data[data["panel"] == panel_name]
        if group.empty:
            continue
        ax.scatter(
            group[x_col],
            group[y_col],
            s=46,
            color=PANEL_COLORS[panel_name],
            marker=PANEL_MARKERS[panel_name],
            edgecolors="white",
            linewidths=0.6,
            alpha=0.88,
            label=PANEL_LABELS[panel_name],
        )

    intercept, slope, r_squared = ols(data[y_col], data[x_col])
    if pd.notna(slope) and pd.notna(intercept):
        x_values = np.linspace(data[x_col].min(), data[x_col].max(), 100)
        ax.plot(
            x_values,
            intercept + slope * x_values,
            color="#333333",
            linestyle="--",
            linewidth=2.0,
            label=f"Fit: {slope:.2f}x, R2={r_squared:.2f}",
        )

    ax.set_title(title, fontweight="bold")
    ax.set_xlabel(x_label, fontweight="bold")
    ax.set_ylabel(y_label, fontweight="bold")
    ax.legend(loc="upper left", framealpha=0.95, fontsize=9)


def plot_event_panel(
    latest_before: pd.DataFrame,
    first_after: pd.DataFrame,
    output_path: Path,
) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(15, 7), facecolor="white")

    x_low, x_high = axis_limits(
        latest_before["survey_change_bps"],
        first_after["sep_change_bps"],
    )
    y_low, y_high = axis_limits(
        latest_before["sep_change_bps"],
        first_after["survey_change_bps"],
    )

    draw_event_panel(
        axes[0],
        latest_before,
        "survey_change_bps",
        "sep_change_bps",
        "Latest Survey Before Each SEP",
        "Latest NY Fed Survey Median Change (bps)",
        "Next SEP Median Change (bps)",
    )
    draw_event_panel(
        axes[1],
        first_after,
        "sep_change_bps",
        "survey_change_bps",
        "First Survey After Each SEP",
        "SEP Median Change (bps)",
        "First Later NY Fed Survey Median Change (bps)",
    )

    for ax in axes:
        ax.set_xlim(x_low, x_high)
        ax.set_ylim(y_low, y_high)

    fig.suptitle(
        "NY Fed Survey and SEP Event Windows",
        fontsize=17,
        fontweight="bold",
        y=0.97,
    )
    add_chart_footer(
        fig,
        "Sources: FRED; FOMC SEP; NY Fed SPD/SMP; author's calculations. "
        "Left: latest survey before SEP. Right: first survey after SEP.",
    )
    plt.tight_layout(rect=(0, 0.065, 1, 0.94))
    plt.savefig(output_path, dpi=150, facecolor="white", bbox_inches="tight")
    plt.close()


def main():
    parser = argparse.ArgumentParser(
        description="Plot latest-before-SEP and first-after-SEP event windows."
    )
    parser.add_argument(
        "--latest-before-csv",
        default="data_out/nyfed_future_sep_predictive_event_analysis.csv",
        type=Path,
        help="Latest-survey-before-SEP event CSV.",
    )
    parser.add_argument(
        "--first-after-csv",
        default="data_out/sep_future_nyfed_predictive_event_analysis.csv",
        type=Path,
        help="First-survey-after-SEP event CSV.",
    )
    parser.add_argument(
        "--output-png",
        default="data_out/sep_survey_event_panel.png",
        type=Path,
        help="Output PNG path.",
    )
    args = parser.parse_args()

    latest_before = pd.read_csv(
        args.latest_before_csv,
        parse_dates=["future_sep_date", "prior_sep_date", "received_by_date"],
    )
    first_after = pd.read_csv(
        args.first_after_csv,
        parse_dates=["sep_date", "previous_sep_date", "received_by_date"],
    )

    args.output_png.parent.mkdir(parents=True, exist_ok=True)
    plot_event_panel(latest_before, first_after, args.output_png)

    latest_intercept, latest_slope, latest_r2 = ols(
        latest_before["sep_change_bps"],
        latest_before["survey_change_bps"],
    )
    first_intercept, first_slope, first_r2 = ols(
        first_after["survey_change_bps"],
        first_after["sep_change_bps"],
    )
    print(f"Saved event-window panel to {args.output_png}")
    print(
        "Latest-before fit: "
        f"slope={latest_slope:.3f}, R2={latest_r2:.3f}; "
        "first-after fit: "
        f"slope={first_slope:.3f}, R2={first_r2:.3f}"
    )


if __name__ == "__main__":
    main()
