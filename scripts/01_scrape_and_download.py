#!/usr/bin/env python3
"""
Step 1: Scrape manifest and download all files (XLSX and PDF).

Usage:
    python scripts/01_scrape_and_download.py --start-year 2011 --end-year 2025
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import click
from src.utils import logger
from src.scrape_manifest import scrape_manifest
from src.download import download_all_meetings


@click.command()
@click.option("--start-year", default=2011, type=int, help="Start year")
@click.option("--end-year", default=2025, type=int, help="End year")
@click.option("--data-dir", default="data_raw", type=click.Path(path_type=Path))
@click.option("--redownload", is_flag=True, default=False, help="Force re-download")
def main(start_year: int, end_year: int, data_dir: Path, redownload: bool):
    """Scrape NY Fed survey page and download all files."""
    
    logger.info("=" * 60)
    logger.info("Step 1: Scrape and Download Survey Files")
    logger.info("=" * 60)
    
    data_dir.mkdir(parents=True, exist_ok=True)
    
    # Scrape manifest
    logger.info(f"Scraping manifest for {start_year}-{end_year}...")
    meetings = scrape_manifest(start_year=start_year, end_year=end_year)
    logger.info(f"Found {len(meetings)} meetings")
    
    # Download all files (XLSX and PDF)
    logger.info("Downloading files...")
    downloaded = download_all_meetings(
        meetings=meetings,
        data_dir=data_dir,
        prefer_xlsx=False,  # Download both XLSX and PDF
        force=redownload,
    )
    
    # Summary
    xlsx_count = sum(1 for _, link, _ in downloaded if link.file_type == "xlsx")
    pdf_count = sum(1 for _, link, _ in downloaded if link.file_type == "pdf")
    
    logger.info("=" * 60)
    logger.info("DOWNLOAD COMPLETE")
    logger.info(f"  XLSX files: {xlsx_count}")
    logger.info(f"  PDF files: {pdf_count}")
    logger.info(f"  Total: {len(downloaded)}")
    logger.info(f"  Location: {data_dir.absolute()}")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()

