#!/usr/bin/env python3
"""
Generate chart of FOMC SEP longer-run federal funds rate estimates.

Matches the styling of plot_rates.py (NY Fed chart).

Reads: data_out/sep_summary.csv
Outputs: data_out/sep_longrun_chart.png
"""

import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from pathlib import Path


def main():
    # Load data
    data_path = Path("data_out/sep_summary.csv")
    if not data_path.exists():
        print(f"Error: {data_path} not found. Run sep_02_extract_dotplot.py first.")
        return

    df = pd.read_csv(data_path, parse_dates=["meeting_date"])

    # Filter to longer-run horizon
    df = df[df["horizon"].str.lower().str.contains("longer")].copy()
    df = df.sort_values("meeting_date")

    if df.empty:
        print("No 'Longer run' horizon data found.")
        return

    print(f"Plotting {len(df)} SEP meetings with longer-run estimates")

    # Create figure (matching plot_rates.py style)
    fig, ax = plt.subplots(figsize=(14, 7), facecolor="white")
    ax.set_facecolor("white")

    # Color scheme (matching NY Fed chart)
    color_sep = "#1a5f7a"  # Deep teal

    # IQR shading
    ax.fill_between(
        df["meeting_date"],
        df["p25"],
        df["p75"],
        alpha=0.2,
        color=color_sep,
        label="25th-75th Pctl"
    )

    # 25th and 75th as dotted lines
    ax.plot(
        df["meeting_date"],
        df["p25"],
        linestyle=":",
        linewidth=1.2,
        color=color_sep,
        alpha=0.6
    )
    ax.plot(
        df["meeting_date"],
        df["p75"],
        linestyle=":",
        linewidth=1.2,
        color=color_sep,
        alpha=0.6
    )

    # Median as solid line with markers
    ax.plot(
        df["meeting_date"],
        df["p50"],
        linestyle="-",
        linewidth=2.5,
        color=color_sep,
        marker="o",
        markersize=3,
        label="Median"
    )

    # Formatting
    ax.set_xlabel("SEP Meeting Date", fontsize=12, fontweight="bold")
    ax.set_ylabel("Longer-Run Fed Funds Rate (%)", fontsize=12, fontweight="bold")
    ax.set_title(
        "FOMC SEP: Longer-Run Federal Funds Rate Estimates",
        fontsize=16,
        fontweight="bold",
        pad=15
    )

    # X-axis
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax.xaxis.set_major_locator(mdates.YearLocator())
    plt.xticks(rotation=45, ha="right")

    # Grid
    ax.grid(True, alpha=0.3, linestyle="-", linewidth=0.5)
    ax.set_axisbelow(True)

    # Spines
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    # Y-axis limits
    y_min = df["p25"].min() - 0.25
    y_max = df["p75"].max() + 0.25
    ax.set_ylim(max(0, y_min), y_max)

    # Legend
    ax.legend(loc="upper right", framealpha=0.95, fontsize=10)

    # Source note
    ax.text(
        0.01, 0.02,
        f"Source: Federal Reserve Summary of Economic Projections | n={len(df)} meetings",
        transform=ax.transAxes,
        fontsize=9,
        color="#666666",
        style="italic"
    )

    plt.tight_layout()

    # Save
    output_path = Path("data_out/sep_longrun_chart.png")
    plt.savefig(output_path, dpi=150, facecolor="white", bbox_inches="tight")
    plt.close()

    print(f"Chart saved to {output_path}")
    print(f"  Date range: {df['meeting_date'].min().strftime('%Y-%m-%d')} to {df['meeting_date'].max().strftime('%Y-%m-%d')}")
    print(f"  Median range: {df['p50'].min():.2f}% to {df['p50'].max():.2f}%")


if __name__ == "__main__":
    main()
