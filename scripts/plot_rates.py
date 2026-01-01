#!/usr/bin/env python3
"""
Generate chart of longer-run federal funds rate expectations.

Plots Combined panel where available. When only SPD/SMP exist,
shows both as separate markers.
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
    
    # Prepare data for plotting
    combined_data = []
    spd_only_data = []
    smp_only_data = []
    
    for date, group in df.groupby("survey_date"):
        panels = set(group["panel"].unique())
        
        if "Combined" in panels:
            # Use Combined
            row = group[group["panel"] == "Combined"].iloc[0]
            combined_data.append({
                "date": date,
                "pctl25": row["pctl25"],
                "pctl50": row["pctl50"],
                "pctl75": row["pctl75"],
            })
        elif "SPD" in panels and "SMP" in panels:
            # Both SPD and SMP but no Combined - plot separately
            spd_row = group[group["panel"] == "SPD"].iloc[0]
            smp_row = group[group["panel"] == "SMP"].iloc[0]
            spd_only_data.append({
                "date": date,
                "pctl25": spd_row["pctl25"],
                "pctl50": spd_row["pctl50"],
                "pctl75": spd_row["pctl75"],
            })
            smp_only_data.append({
                "date": date,
                "pctl25": smp_row["pctl25"],
                "pctl50": smp_row["pctl50"],
                "pctl75": smp_row["pctl75"],
            })
        elif "SPD" in panels:
            # Only SPD
            row = group[group["panel"] == "SPD"].iloc[0]
            combined_data.append({
                "date": date,
                "pctl25": row["pctl25"],
                "pctl50": row["pctl50"],
                "pctl75": row["pctl75"],
            })
        elif "SMP" in panels:
            # Only SMP
            row = group[group["panel"] == "SMP"].iloc[0]
            combined_data.append({
                "date": date,
                "pctl25": row["pctl25"],
                "pctl50": row["pctl50"],
                "pctl75": row["pctl75"],
            })
    
    df_combined = pd.DataFrame(combined_data).sort_values("date") if combined_data else pd.DataFrame()
    df_spd = pd.DataFrame(spd_only_data).sort_values("date") if spd_only_data else pd.DataFrame()
    df_smp = pd.DataFrame(smp_only_data).sort_values("date") if smp_only_data else pd.DataFrame()
    
    # Create figure
    fig, ax = plt.subplots(figsize=(14, 7), facecolor="white")
    ax.set_facecolor("white")
    
    # Color scheme
    color_combined = "#1a5f7a"  # Deep teal
    color_spd = "#e63946"       # Red
    color_smp = "#2a9d8f"       # Teal green
    
    # Plot Combined/single panel data
    if not df_combined.empty:
        # IQR shading
        ax.fill_between(
            df_combined["date"], 
            df_combined["pctl25"], 
            df_combined["pctl75"],
            alpha=0.2, 
            color=color_combined,
            label="25th-75th Percentile"
        )
        
        # 25th and 75th as dotted lines
        ax.plot(
            df_combined["date"], 
            df_combined["pctl25"],
            linestyle=":", 
            linewidth=1.5, 
            color=color_combined,
            alpha=0.7
        )
        ax.plot(
            df_combined["date"], 
            df_combined["pctl75"],
            linestyle=":", 
            linewidth=1.5, 
            color=color_combined,
            alpha=0.7
        )
        
        # Median as solid line
        ax.plot(
            df_combined["date"], 
            df_combined["pctl50"],
            linestyle="-", 
            linewidth=2.5, 
            color=color_combined,
            marker="o",
            markersize=3,
            label="Median (Combined/Single)"
        )
    
    # Plot SPD-only dates
    if not df_spd.empty:
        ax.scatter(
            df_spd["date"], 
            df_spd["pctl50"],
            color=color_spd,
            marker="^",
            s=60,
            zorder=5,
            label="SPD Median",
            edgecolors="white",
            linewidths=0.5
        )
        # Vertical lines for IQR
        for _, row in df_spd.iterrows():
            ax.plot(
                [row["date"], row["date"]], 
                [row["pctl25"], row["pctl75"]],
                color=color_spd,
                linewidth=1.5,
                alpha=0.5
            )
    
    # Plot SMP-only dates  
    if not df_smp.empty:
        ax.scatter(
            df_smp["date"], 
            df_smp["pctl50"],
            color=color_smp,
            marker="v",
            s=60,
            zorder=5,
            label="SMP Median",
            edgecolors="white",
            linewidths=0.5
        )
        # Vertical lines for IQR
        for _, row in df_smp.iterrows():
            ax.plot(
                [row["date"], row["date"]], 
                [row["pctl25"], row["pctl75"]],
                color=color_smp,
                linewidth=1.5,
                alpha=0.5
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
    for data in [df_combined, df_spd, df_smp]:
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
    total_dates = len(df_combined) + len(df_spd)
    ax.text(
        0.01, 0.02,
        f"Source: NY Fed Survey of Primary Dealers & Market Participants | n={total_dates} surveys",
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
    print(f"  Combined/single panel points: {len(df_combined)}")
    print(f"  SPD-only points: {len(df_spd)}")
    print(f"  SMP-only points: {len(df_smp)}")


if __name__ == "__main__":
    main()

