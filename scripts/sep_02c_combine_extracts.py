#!/usr/bin/env python3
"""
Combine SEP extracts from HTML pages (2020+) and PDFs (2012-2019).

Reads:
  - data_out/sep_summary.csv (HTML extracts, 2020+)
  - data_out/sep_pdf_extracts.csv (PDF extracts, 2012-2019)

Outputs:
  - data_out/sep_summary_combined.csv (merged dataset)
  - Updates data_out/sep_summary.csv with combined data
"""

import pandas as pd
from pathlib import Path


def main():
    html_path = Path("data_out/sep_summary.csv")
    pdf_path = Path("data_out/sep_pdf_extracts.csv")
    output_path = Path("data_out/sep_summary.csv")
    backup_path = Path("data_out/sep_summary_html_only.csv")

    print("Combining SEP extracts...")

    # Load HTML extracts (2020+)
    if html_path.exists():
        df_html = pd.read_csv(html_path, parse_dates=["meeting_date"])
        # Filter to only "Longer run" horizon for consistency
        df_html = df_html[df_html["horizon"].str.lower().str.contains("longer")].copy()
        df_html["source"] = "html"
        print(f"  HTML extracts: {len(df_html)} rows")
    else:
        print(f"  Warning: {html_path} not found")
        df_html = pd.DataFrame()

    # Load PDF extracts (2012-2019)
    if pdf_path.exists():
        df_pdf = pd.read_csv(pdf_path, parse_dates=["meeting_date"])
        # Filter to only valid extracts with data
        df_pdf = df_pdf[df_pdf["p50"].notna()].copy()
        print(f"  PDF extracts: {len(df_pdf)} rows")
    else:
        print(f"  Warning: {pdf_path} not found")
        df_pdf = pd.DataFrame()

    if df_html.empty and df_pdf.empty:
        print("No data to combine!")
        return

    # Backup original HTML-only data
    if not df_html.empty:
        df_html.to_csv(backup_path, index=False)
        print(f"  Backed up HTML data to {backup_path}")

    # Standardize columns for merge
    common_cols = ["meeting_date", "horizon", "n", "p25", "p50", "p75", "source"]

    if not df_html.empty:
        # Ensure HTML has source column
        if "source" not in df_html.columns:
            df_html["source"] = "html"
        df_html = df_html[common_cols].copy()

    if not df_pdf.empty:
        df_pdf = df_pdf[common_cols].copy()

    # Combine datasets
    if not df_html.empty and not df_pdf.empty:
        df_combined = pd.concat([df_pdf, df_html], ignore_index=True)
    elif not df_html.empty:
        df_combined = df_html
    else:
        df_combined = df_pdf

    # Sort by meeting date
    df_combined = df_combined.sort_values("meeting_date").reset_index(drop=True)

    # Remove duplicates (prefer HTML over PDF if same date)
    df_combined = df_combined.drop_duplicates(
        subset=["meeting_date", "horizon"],
        keep="last"  # Keep HTML (comes after PDF in sorted concat)
    )

    # Save combined data
    df_combined.to_csv(output_path, index=False)

    print(f"\nCombined dataset:")
    print(f"  Total rows: {len(df_combined)}")
    print(f"  Date range: {df_combined['meeting_date'].min()} to {df_combined['meeting_date'].max()}")
    print(f"  From HTML: {len(df_combined[df_combined['source'] == 'html'])}")
    print(f"  From PDF: {len(df_combined[df_combined['source'] == 'sep_pdf'])}")
    print(f"  Saved to: {output_path}")


if __name__ == "__main__":
    main()
