#!/usr/bin/env python3
"""
Run the complete pipeline: download, extract, and combine data.

Usage:
    export OPENAI_API_KEY="your-key"
    python scripts/run_all.py
"""

import subprocess
import sys
from pathlib import Path


def run_step(script: str, extra_args: list = None):
    """Run a script and check for errors."""
    cmd = [sys.executable, script]
    if extra_args:
        cmd.extend(extra_args)
    
    print(f"\n{'='*60}")
    print(f"Running: {' '.join(cmd)}")
    print("="*60 + "\n")
    
    result = subprocess.run(cmd, cwd=Path(__file__).parent.parent)
    
    if result.returncode != 0:
        print(f"\nError: {script} failed with code {result.returncode}")
        sys.exit(result.returncode)


def main():
    scripts_dir = Path(__file__).parent
    
    print("\n" + "="*60)
    print("NY FED SURVEY DATA PIPELINE")
    print("="*60)
    
    # Step 1: Refresh manifest/download cache. Existing files are skipped by
    # the downloader unless --redownload is passed to that script directly.
    run_step(str(scripts_dir / "01_scrape_and_download.py"))
    
    # Step 2: Extract from XLSX
    run_step(str(scripts_dir / "02_extract_xlsx.py"))
    
    # Step 3: Extract from PDF with LLM
    run_step(str(scripts_dir / "03_extract_pdf_llm.py"))

    # Step 4: Extract survey distribution/receipt metadata
    run_step(str(scripts_dir / "extract_survey_receipt_dates.py"))
    
    # Step 5: Combine data
    run_step(str(scripts_dir / "04_combine_and_plot.py"))
    
    print("\n" + "="*60)
    print("PIPELINE COMPLETE!")
    print("="*60)
    print("Output: data_out/nyfed_ff_longrun_percentiles.csv")
    print("="*60 + "\n")


if __name__ == "__main__":
    main()
