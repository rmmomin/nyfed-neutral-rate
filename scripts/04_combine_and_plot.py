#!/usr/bin/env python3
"""
Step 4: Combine XLSX and PDF extracts into final CSV.

Usage:
    python scripts/04_combine_and_plot.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import click
import pandas as pd


@click.command()
@click.option("--xlsx-csv", default="data_out/xlsx_extracts.csv", type=click.Path(path_type=Path))
@click.option("--pdf-csv", default="data_out/pdf_extracts.csv", type=click.Path(path_type=Path))
@click.option("--output", default="data_out/nyfed_ff_longrun_percentiles.csv", type=click.Path(path_type=Path))
def main(xlsx_csv: Path, pdf_csv: Path, output: Path):
    """Combine XLSX and PDF extracts into final CSV."""
    
    print("=" * 60)
    print("Step 4: Combine Data")
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
    
    print("=" * 60)
    print("COMPLETE")
    print(f"  Combined CSV: {output.absolute()}")
    print("=" * 60)


if __name__ == "__main__":
    main()
