#!/usr/bin/env python3
"""
Generate chart of longer-run federal funds rate expectations.

SPD (Primary Dealers) shown as a continuous line.
SMP and Combined shown as markers.
"""

import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from pathlib import Path


def main():
    # Load data
    data_path = Path("data_out/nyfed_ff_longrun_percentiles.csv")
    df = pd.read_csv(data_path, parse_dates=["survey_date"])
    
    # Filter to rows with valid median
    df = df[df["pctl50"].notna()].copy()
    
    # Separate data by panel type
    df_spd = df[df["panel"] == "SPD"].copy().sort_values("survey_date")
    df_smp = df[df["panel"] == "SMP"].copy().sort_values("survey_date")
    df_combined = df[df["panel"] == "Combined"].copy().sort_values("survey_date")
    
    # Create figure
    fig, ax = plt.subplots(figsize=(14, 7), facecolor="white")
    ax.set_facecolor("white")
    
    # Color scheme
    color_spd = "#1a5f7a"       # Deep teal for SPD line
    color_smp = "#2a9d8f"       # Teal green for SMP markers
    color_combined = "#e63946"  # Red for Combined markers
    
    # Plot SPD as continuous line with IQR shading
    if not df_spd.empty:
        # IQR shading for SPD
        ax.fill_between(
            df_spd["survey_date"], 
            df_spd["pctl25"], 
            df_spd["pctl75"],
            alpha=0.2, 
            color=color_spd,
            label="SPD 25th-75th Pctl"
        )
        
        # 25th and 75th as dotted lines
        ax.plot(
            df_spd["survey_date"], 
            df_spd["pctl25"],
            linestyle=":", 
            linewidth=1.2, 
            color=color_spd,
            alpha=0.6
        )
        ax.plot(
            df_spd["survey_date"], 
            df_spd["pctl75"],
            linestyle=":", 
            linewidth=1.2, 
            color=color_spd,
            alpha=0.6
        )
        
        # SPD Median as solid line
        ax.plot(
            df_spd["survey_date"], 
            df_spd["pctl50"],
            linestyle="-", 
            linewidth=2.5, 
            color=color_spd,
            marker="o",
            markersize=3,
            label="SPD Median"
        )
    
    # Plot SMP as markers
    if not df_smp.empty:
        ax.scatter(
            df_smp["survey_date"], 
            df_smp["pctl50"],
            color=color_smp,
            marker="v",
            s=50,
            zorder=5,
            label="SMP Median",
            edgecolors="white",
            linewidths=0.5,
            alpha=0.8
        )
        # Vertical lines for IQR
        for _, row in df_smp.iterrows():
            ax.plot(
                [row["survey_date"], row["survey_date"]], 
                [row["pctl25"], row["pctl75"]],
                color=color_smp,
                linewidth=1.2,
                alpha=0.4
            )
    
    # Plot Combined as markers
    if not df_combined.empty:
        ax.scatter(
            df_combined["survey_date"], 
            df_combined["pctl50"],
            color=color_combined,
            marker="s",
            s=50,
            zorder=5,
            label="Combined Median",
            edgecolors="white",
            linewidths=0.5,
            alpha=0.8
        )
        # Vertical lines for IQR
        for _, row in df_combined.iterrows():
            ax.plot(
                [row["survey_date"], row["survey_date"]], 
                [row["pctl25"], row["pctl75"]],
                color=color_combined,
                linewidth=1.2,
                alpha=0.4
            )
    
    # Formatting
    ax.set_xlabel("Survey Date", fontsize=12, fontweight="bold")
    ax.set_ylabel("Longer-Run Fed Funds Rate (%)", fontsize=12, fontweight="bold")
    ax.set_title(
        "NY Fed Survey: Longer-Run Federal Funds Rate Expectations",
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
    all_values = []
    for data in [df_spd, df_smp, df_combined]:
        if not data.empty:
            all_values.extend(data["pctl25"].dropna().tolist())
            all_values.extend(data["pctl50"].dropna().tolist())
            all_values.extend(data["pctl75"].dropna().tolist())
    
    if all_values:
        y_min = min(all_values) - 0.25
        y_max = max(all_values) + 0.25
        ax.set_ylim(max(0, y_min), y_max)
    
    # Legend
    ax.legend(loc="upper right", framealpha=0.95, fontsize=10)
    
    # Source note
    total_surveys = len(df_spd) + len(df_smp) + len(df_combined)
    ax.text(
        0.01, 0.02,
        f"Source: NY Fed Survey of Primary Dealers & Market Participants | n={total_surveys} observations",
        transform=ax.transAxes,
        fontsize=9,
        color="#666666",
        style="italic"
    )
    
    plt.tight_layout()
    
    # Save
    output_path = Path("data_out/longrun_rate_chart.png")
    plt.savefig(output_path, dpi=150, facecolor="white", bbox_inches="tight")
    plt.close()
    
    print(f"Chart saved to {output_path}")
    print(f"  SPD points: {len(df_spd)}")
    print(f"  SMP points: {len(df_smp)}")
    print(f"  Combined points: {len(df_combined)}")


if __name__ == "__main__":
    main()
