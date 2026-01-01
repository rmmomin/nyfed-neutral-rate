#!/usr/bin/env python3
"""
Step 4: Combine XLSX and PDF extracts, generate final CSV and plots.

Usage:
    python scripts/04_combine_and_plot.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import click
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime


@click.command()
@click.option("--xlsx-csv", default="data_out/xlsx_extracts.csv", type=click.Path(path_type=Path))
@click.option("--pdf-csv", default="data_out/pdf_extracts.csv", type=click.Path(path_type=Path))
@click.option("--output", default="data_out/nyfed_ff_longrun_percentiles.csv", type=click.Path(path_type=Path))
@click.option("--plot-output", default="data_out/longrun_rate_chart.png", type=click.Path(path_type=Path))
def main(xlsx_csv: Path, pdf_csv: Path, output: Path, plot_output: Path):
    """Combine extracts and generate plots."""
    
    print("=" * 60)
    print("Step 4: Combine Data and Generate Plots")
    print("=" * 60)
    
    output.parent.mkdir(parents=True, exist_ok=True)
    
    dfs = []
    
    # Load XLSX extracts
    if xlsx_csv.exists():
        df_xlsx = pd.read_csv(xlsx_csv)
        print(f"Loaded {len(df_xlsx)} rows from XLSX extracts")
        dfs.append(df_xlsx)
    else:
        print(f"Warning: {xlsx_csv} not found")
    
    # Load PDF extracts
    if pdf_csv.exists():
        df_pdf = pd.read_csv(pdf_csv)
        print(f"Loaded {len(df_pdf)} rows from PDF extracts")
        dfs.append(df_pdf)
    else:
        print(f"Warning: {pdf_csv} not found")
    
    if not dfs:
        print("Error: No data to combine!")
        sys.exit(1)
    
    # Combine
    df = pd.concat(dfs, ignore_index=True)
    df["survey_date"] = pd.to_datetime(df["survey_date"])
    
    # Prefer XLSX over PDF when both exist for same date
    df["source_priority"] = df["source"].map({
        "xlsx": 0, 
        "pdf_llm": 1, 
        "pdf_text": 2, 
        "pdf_ocr": 3, 
        "pdf_openai": 1
    }).fillna(9)
    df = df.sort_values(["survey_date", "panel", "source_priority"])
    
    # Keep first (best source) for each date/panel combo
    df = df.drop_duplicates(subset=["survey_date", "panel"], keep="first")
    df = df.drop(columns=["source_priority"])
    
    # Sort by date
    df = df.sort_values("survey_date")
    
    # Save combined CSV
    df.to_csv(output, index=False)
    print(f"Saved {len(df)} records to {output}")
    
    # Generate plot
    print("\nGenerating plot...")
    generate_plot(df, plot_output)
    
    print("=" * 60)
    print("COMPLETE")
    print(f"  Combined CSV: {output.absolute()}")
    print(f"  Plot: {plot_output.absolute()}")
    print("=" * 60)


def generate_plot(df: pd.DataFrame, output: Path):
    """Generate time series plot of longer-run rate expectations."""
    
    # Filter for rows with valid median
    df_valid = df[df["pctl50"].notna()].copy()
    
    if df_valid.empty:
        print("Warning: No valid data to plot!")
        return
    
    # Aggregate by date - take Combined if available, otherwise average across panels
    results = []
    for date, group in df_valid.groupby("survey_date"):
        combined = group[group["panel"] == "Combined"]
        if not combined.empty:
            row = combined.iloc[0]
            results.append({
                "survey_date": date,
                "pctl25": row["pctl25"],
                "pctl50": row["pctl50"],
                "pctl75": row["pctl75"],
            })
        else:
            # Average across panels
            results.append({
                "survey_date": date,
                "pctl25": group["pctl25"].mean(),
                "pctl50": group["pctl50"].mean(),
                "pctl75": group["pctl75"].mean(),
            })
    
    df_agg = pd.DataFrame(results)
    df_agg = df_agg.sort_values("survey_date")
    
    # Convert dates
    df_agg["survey_date"] = pd.to_datetime(df_agg["survey_date"])
    
    print(f"Plotting {len(df_agg)} data points from {df_agg['survey_date'].min().strftime('%Y-%m')} to {df_agg['survey_date'].max().strftime('%Y-%m')}")
    
    # Create figure with white background
    fig, ax = plt.subplots(figsize=(14, 7), facecolor='white')
    ax.set_facecolor('white')
    
    dates = df_agg["survey_date"]
    pctl25 = df_agg["pctl25"].astype(float)
    pctl50 = df_agg["pctl50"].astype(float)
    pctl75 = df_agg["pctl75"].astype(float)
    
    # Plot shaded area for IQR
    ax.fill_between(
        dates, pctl25, pctl75,
        alpha=0.3, color="#2E86AB",
        label="25th-75th Percentile Range"
    )
    
    # Plot percentile lines
    ax.plot(dates, pctl25, 
            linestyle="--", linewidth=1.2, color="#2E86AB", alpha=0.7,
            label="25th Percentile")
    
    ax.plot(dates, pctl75, 
            linestyle="--", linewidth=1.2, color="#2E86AB", alpha=0.7,
            label="75th Percentile")
    
    # Median line (solid, prominent)
    ax.plot(dates, pctl50, 
            linestyle="-", linewidth=2.5, color="#E94F37",
            marker="o", markersize=4, markerfacecolor="#E94F37",
            label="Median (50th Pctl)")
    
    # Formatting
    ax.set_xlabel("Survey Date", fontsize=12, fontweight='bold')
    ax.set_ylabel("Expected Longer-Run Fed Funds Rate (%)", fontsize=12, fontweight='bold')
    ax.set_title(
        "NY Fed Survey: Longer-Run Federal Funds Rate Expectations",
        fontsize=16, fontweight="bold", pad=15
    )
    
    # X-axis formatting
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax.xaxis.set_major_locator(mdates.YearLocator())
    plt.xticks(rotation=45, ha='right')
    
    # Grid
    ax.grid(True, alpha=0.3, linestyle='-', linewidth=0.5)
    ax.set_axisbelow(True)
    
    # Spines
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    
    # Y-axis range with padding
    y_min = min(pctl25.min(), pctl50.min()) - 0.25
    y_max = max(pctl75.max(), pctl50.max()) + 0.25
    ax.set_ylim(max(0, y_min), y_max)
    
    # Legend
    ax.legend(loc="upper right", framealpha=0.9, fontsize=10)
    
    # Source note
    ax.text(
        0.01, 0.02,
        f"Source: NY Fed Survey of Primary Dealers & Market Participants | n={len(df_agg)} surveys",
        transform=ax.transAxes, fontsize=9, color="#666666", style='italic'
    )
    
    plt.tight_layout()
    plt.savefig(output, dpi=150, facecolor='white', edgecolor='none', bbox_inches='tight')
    plt.close()
    
    print(f"Plot saved: {output}")


if __name__ == "__main__":
    main()
