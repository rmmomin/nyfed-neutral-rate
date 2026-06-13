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
@click.option("--receipt-csv", default="data_out/nyfed_survey_receipt_dates.csv", type=click.Path(path_type=Path))
@click.option("--output", default="data_out/nyfed_ff_longrun_percentiles.csv", type=click.Path(path_type=Path))
def main(xlsx_csv: Path, pdf_csv: Path, receipt_csv: Path, output: Path):
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

    # Attach survey distribution/receipt deadlines when available.
    df = attach_receipt_dates(df, receipt_csv)
    
    # Save combined CSV
    df.to_csv(output, index=False)
    print(f"Saved {len(df)} records to {output}")
    
    print("=" * 60)
    print("COMPLETE")
    print(f"  Combined CSV: {output.absolute()}")
    print("=" * 60)


def attach_receipt_dates(df: pd.DataFrame, receipt_csv: Path) -> pd.DataFrame:
    """Attach distributed and received-by dates to each survey observation."""
    receipt_cols = ["distributed_date", "received_by_date", "receipt_source_file"]

    if not receipt_csv.exists():
        print(f"Warning: {receipt_csv} not found")
        for col in receipt_cols:
            df[col] = pd.NA
        return df

    receipts = pd.read_csv(
        receipt_csv,
        parse_dates=["survey_date", "distributed_date", "received_by_date"],
    )
    receipts = receipts[receipts["received_by_date"].notna()].copy()
    if receipts.empty:
        print(f"Warning: {receipt_csv} has no received_by_date values")
        for col in receipt_cols:
            df[col] = pd.NA
        return df

    receipts = receipts.rename(columns={"source_file": "receipt_source_file"})
    file_receipts = receipts[[
        "distributed_date",
        "received_by_date",
        "receipt_source_file",
    ]].drop_duplicates(subset=["receipt_source_file"]).copy()
    file_receipts = file_receipts.rename(columns={
        "distributed_date": "distributed_date_file",
        "received_by_date": "received_by_date_file",
        "receipt_source_file": "local_path",
    })

    out = df.merge(file_receipts, on="local_path", how="left")
    out["distributed_date"] = out["distributed_date_file"]
    out["received_by_date"] = out["received_by_date_file"]
    out["receipt_source_file"] = out["local_path"].where(out["received_by_date"].notna(), pd.NA)
    out = out.drop(columns=["distributed_date_file", "received_by_date_file"])

    direct = receipts[[
        "survey_date",
        "panel",
        "distributed_date",
        "received_by_date",
        "receipt_source_file",
    ]].copy()

    out = out.merge(
        direct,
        on=["survey_date", "panel"],
        how="left",
        suffixes=("", "_receipt"),
    )

    for col in receipt_cols:
        receipt_col = f"{col}_receipt"
        if receipt_col in out.columns:
            out[col] = out[col].combine_first(out[receipt_col])
            out = out.drop(columns=[receipt_col])

    # Fallback: if a date has a single common receipt deadline across panels
    # or a Combined/merged survey receipt, use it for unmatched rows.
    fallback_rows = []
    for survey_date, group in receipts.groupby("survey_date"):
        unique_dates = group[["distributed_date", "received_by_date"]].drop_duplicates()
        combined = group[group["panel"] == "Combined"]
        if not combined.empty:
            row = combined.iloc[0]
        elif len(unique_dates) == 1:
            row = group.iloc[0]
        else:
            continue
        fallback_rows.append({
            "survey_date": survey_date,
            "distributed_date_fallback": row["distributed_date"],
            "received_by_date_fallback": row["received_by_date"],
            "receipt_source_file_fallback": row["receipt_source_file"],
        })

    if fallback_rows:
        fallback = pd.DataFrame(fallback_rows)
        out = out.merge(fallback, on="survey_date", how="left")
        out["distributed_date"] = out["distributed_date"].combine_first(out["distributed_date_fallback"])
        out["received_by_date"] = out["received_by_date"].combine_first(out["received_by_date_fallback"])
        out["receipt_source_file"] = out["receipt_source_file"].combine_first(out["receipt_source_file_fallback"])
        out = out.drop(columns=[
            "distributed_date_fallback",
            "received_by_date_fallback",
            "receipt_source_file_fallback",
        ])

    for col in ["survey_date", "distributed_date", "received_by_date"]:
        out[col] = pd.to_datetime(out[col], errors="coerce")

    leading_cols = [
        "survey_date",
        "panel",
        "distributed_date",
        "received_by_date",
        "concept",
        "pctl25",
        "pctl50",
        "pctl75",
    ]
    remaining_cols = [col for col in out.columns if col not in leading_cols]
    return out[leading_cols + remaining_cols]


if __name__ == "__main__":
    main()
