#!/usr/bin/env python3
"""
Step 2: Extract percentiles from XLSX files.

Usage:
    python scripts/02_extract_xlsx.py
"""

import csv
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

import click
from tqdm import tqdm
from src.utils import logger
from src.extract_xlsx import extract_from_xlsx
from src.scrape_manifest import scrape_manifest, parse_date_from_url, MONTH_MAP


def get_survey_date_from_filename(filename: str) -> datetime:
    """Extract survey date from filename like 'oct-2025-data.xlsx'."""
    filename_lower = filename.lower()
    
    # Try pattern like "oct-2025" or "dec-2024"
    import re
    match = re.search(r'(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[^a-z]*(\d{4})', filename_lower)
    if match:
        month_str = match.group(1)
        year = int(match.group(2))
        month = MONTH_MAP.get(month_str, 1)
        return datetime(year, month, 1)
    
    return datetime.now()


@click.command()
@click.option("--data-dir", default="data_raw", type=click.Path(path_type=Path, exists=True))
@click.option("--output", default="data_out/xlsx_extracts.csv", type=click.Path(path_type=Path))
def main(data_dir: Path, output: Path):
    """Extract percentiles from all XLSX files."""
    
    logger.info("=" * 60)
    logger.info("Step 2: Extract Data from XLSX Files")
    logger.info("=" * 60)
    
    output.parent.mkdir(parents=True, exist_ok=True)
    
    # Find all XLSX files
    xlsx_files = sorted(data_dir.glob("*.xlsx"))
    logger.info(f"Found {len(xlsx_files)} XLSX files")
    
    all_results = []
    
    for filepath in tqdm(xlsx_files, desc="Processing XLSX"):
        survey_date = get_survey_date_from_filename(filepath.name)
        
        results = extract_from_xlsx(
            filepath=filepath,
            file_url=str(filepath),
            survey_date=survey_date,
        )
        all_results.extend(results)
    
    # Write CSV
    logger.info(f"Writing {len(all_results)} records to {output}")
    
    with open(output, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "survey_date", "panel", "concept", "pctl25", "pctl50", "pctl75",
            "source", "file_url", "local_path", "pdf_page", "notes"
        ])
        writer.writeheader()
        for r in all_results:
            writer.writerow(r.to_dict())
    
    # Summary
    valid_count = sum(1 for r in all_results if r.pctl50 is not None)
    logger.info("=" * 60)
    logger.info("XLSX EXTRACTION COMPLETE")
    logger.info(f"  Total records: {len(all_results)}")
    logger.info(f"  Valid (has median): {valid_count}")
    logger.info(f"  Output: {output.absolute()}")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()

