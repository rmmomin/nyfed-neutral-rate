#!/usr/bin/env python3
"""
Run full FOMC SEP dot plot pipeline.

Steps:
1. Discover SEP URLs (HTML pages 2020+ and PDFs 2012-2019)
2. Download historical PDFs
3. Extract from HTML pages (2020+)
4. Extract from PDFs using OpenAI API (2012-2019) - requires OPENAI_API_KEY
5. Combine extracts into unified dataset
6. Generate longer-run rate chart

Usage:
    export OPENAI_API_KEY="your-key"
    python scripts/sep_run_all.py
"""

import os
import subprocess
import sys
from pathlib import Path


def run_script(script_name: str, optional: bool = False) -> bool:
    """Run a script and return True if successful."""
    script_path = Path(__file__).parent / script_name
    print(f"\n{'='*60}")
    print(f"Running {script_name}")
    print("=" * 60)

    result = subprocess.run([sys.executable, str(script_path)], cwd=Path(__file__).parent.parent)

    if result.returncode != 0 and optional:
        print(f"  (Optional step failed, continuing...)")
        return True

    return result.returncode == 0


def main():
    print("FOMC SEP Dot Plot Pipeline (with PDF extraction)")
    print("=" * 60)

    # Check for OpenAI API key
    has_api_key = bool(os.environ.get("OPENAI_API_KEY"))
    if not has_api_key:
        print("\nNote: OPENAI_API_KEY not set.")
        print("PDF extraction (2012-2019) will be skipped.")
        print("Set the environment variable to enable full historical data.\n")

    # Core scripts (always run)
    core_scripts = [
        "sep_01_discover_pages.py",      # Discover HTML + PDF URLs
        "sep_02_extract_dotplot.py",     # Extract from HTML (2020+)
    ]

    # PDF extraction scripts (only if API key is set)
    pdf_scripts = [
        "sep_01b_download_pdfs.py",      # Download PDFs
        "sep_02b_extract_pdf_llm.py",    # Extract from PDFs using LLM
        "sep_02c_combine_extracts.py",   # Combine HTML + PDF extracts
    ]

    # Final scripts
    final_scripts = [
        "sep_03_plot_longrun.py",        # Generate chart
    ]

    # Run core scripts
    for script in core_scripts:
        if not run_script(script):
            print(f"\nError: {script} failed")
            sys.exit(1)

    # Run PDF extraction if API key is available
    if has_api_key:
        for script in pdf_scripts:
            if not run_script(script):
                print(f"\nError: {script} failed")
                sys.exit(1)

    # Run final scripts
    for script in final_scripts:
        if not run_script(script):
            print(f"\nError: {script} failed")
            sys.exit(1)

    print("\n" + "=" * 60)
    print("Pipeline complete!")
    print("=" * 60)
    print("\nOutputs:")
    print("  data_out/sep_page_urls.txt      - HTML page URLs (2020+)")
    print("  data_out/sep_pdf_urls.txt       - PDF URLs (2012-2019)")
    print("  data_out/sep_dots.csv           - Individual dot values")
    print("  data_out/sep_summary.csv        - Percentile summary (combined)")
    print("  data_out/sep_longrun_chart.png  - Longer-run rate chart")
    if has_api_key:
        print("  data_out/sep_pdf_extracts.csv   - PDF extraction results")


if __name__ == "__main__":
    main()
