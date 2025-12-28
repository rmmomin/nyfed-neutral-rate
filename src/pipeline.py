"""
Main CLI pipeline for extracting NY Fed longer-run federal funds rate percentiles.

This module orchestrates:
1. Scraping the manifest of survey files
2. Downloading XLSX and PDF files
3. Extracting percentiles from files
4. Outputting a tidy CSV

Usage:
    python -m src.pipeline --start-year 2011 --end-year 2025
"""

import csv
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import click
from tqdm import tqdm

from .utils import (
    logger,
    ExtractedPercentile,
    CONCEPT_FF_LONGER_RUN,
    PANEL_COMBINED,
    SOURCE_XLSX,
)
from .scrape_manifest import scrape_manifest, SurveyMeeting
from .download import download_all_meetings
from .extract_xlsx import extract_from_xlsx
from .extract_pdf import extract_from_pdf


# Default paths
DEFAULT_DATA_RAW = Path("data_raw")
DEFAULT_DATA_OUT = Path("data_out")
DEFAULT_OUTPUT_FILE = "nyfed_ff_longrun_percentiles.csv"

# CSV columns
CSV_COLUMNS = [
    "survey_date",
    "panel",
    "concept",
    "pctl25",
    "pctl50",
    "pctl75",
    "source",
    "file_url",
    "local_path",
    "pdf_page",
    "notes",
]


def write_csv(
    results: List[ExtractedPercentile],
    output_path: Path,
) -> None:
    """Write extracted percentiles to a CSV file."""
    logger.info(f"Writing {len(results)} rows to {output_path}")
    
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        
        for result in results:
            writer.writerow(result.to_dict())
    
    logger.info(f"CSV written successfully: {output_path}")


def process_meeting(
    meeting: SurveyMeeting,
    data_dir: Path,
    use_ocr: bool = True,
    prefer_xlsx: bool = True,
) -> List[ExtractedPercentile]:
    """
    Process a single meeting, downloading and extracting data.
    
    Returns extracted percentiles for this meeting.
    """
    results = []
    
    xlsx_links = meeting.get_xlsx_links()
    pdf_links = meeting.get_pdf_links()
    
    # Prefer XLSX if available
    if xlsx_links:
        for link in xlsx_links:
            local_path = data_dir / Path(link.url).name.split("?")[0]
            
            if local_path.exists():
                extracted = extract_from_xlsx(
                    filepath=local_path,
                    file_url=link.url,
                    survey_date=meeting.meeting_date,
                    survey_type=link.survey_type,
                )
                results.extend(extracted)
    
    # Fall back to PDF if no XLSX or XLSX extraction failed
    if not results or all(r.pctl25 is None and r.pctl50 is None and r.pctl75 is None for r in results):
        if pdf_links:
            for link in pdf_links:
                local_path = data_dir / Path(link.url).name.split("?")[0]
                
                if local_path.exists():
                    extracted = extract_from_pdf(
                        filepath=local_path,
                        file_url=link.url,
                        survey_date=meeting.meeting_date,
                        survey_type=link.survey_type,
                        use_ocr=use_ocr,
                    )
                    results.extend(extracted)
    
    # If no results at all, create a placeholder
    if not results:
        # Use first available link for metadata
        first_link = xlsx_links[0] if xlsx_links else (pdf_links[0] if pdf_links else None)
        
        results.append(ExtractedPercentile(
            survey_date=meeting.meeting_date,
            panel=PANEL_COMBINED,
            concept=CONCEPT_FF_LONGER_RUN,
            pctl25=None,
            pctl50=None,
            pctl75=None,
            source=SOURCE_XLSX if xlsx_links else "pdf_text",
            file_url=first_link.url if first_link else "",
            local_path="",
            notes="no_data_extracted",
        ))
    
    return results


@click.command()
@click.option(
    "--start-year",
    default=2011,
    type=int,
    help="Earliest year to include (default: 2011)",
)
@click.option(
    "--end-year",
    default=2025,
    type=int,
    help="Latest year to include (default: 2025)",
)
@click.option(
    "--data-dir",
    default=str(DEFAULT_DATA_RAW),
    type=click.Path(path_type=Path),
    help="Directory for downloaded files (default: data_raw/)",
)
@click.option(
    "--output-dir",
    default=str(DEFAULT_DATA_OUT),
    type=click.Path(path_type=Path),
    help="Directory for output CSV (default: data_out/)",
)
@click.option(
    "--output-file",
    default=DEFAULT_OUTPUT_FILE,
    type=str,
    help="Output CSV filename (default: nyfed_ff_longrun_percentiles.csv)",
)
@click.option(
    "--redownload",
    is_flag=True,
    default=False,
    help="Force re-download of existing files",
)
@click.option(
    "--use-ocr",
    is_flag=True,
    default=True,
    help="Enable OCR for PDFs when text extraction fails (default: True)",
)
@click.option(
    "--no-ocr",
    is_flag=True,
    default=False,
    help="Disable OCR for PDFs",
)
@click.option(
    "--max-files",
    default=None,
    type=int,
    help="Maximum number of files to download (for testing)",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    default=False,
    help="Enable verbose/debug logging",
)
@click.option(
    "--skip-download",
    is_flag=True,
    default=False,
    help="Skip download step (use existing files in data_dir)",
)
def main(
    start_year: int,
    end_year: int,
    data_dir: Path,
    output_dir: Path,
    output_file: str,
    redownload: bool,
    use_ocr: bool,
    no_ocr: bool,
    max_files: Optional[int],
    verbose: bool,
    skip_download: bool,
):
    """
    Extract NY Fed longer-run federal funds rate percentiles.
    
    This tool scrapes the NY Fed Survey of Market Expectations page,
    downloads survey data files (XLSX preferred, PDF fallback),
    and extracts 25th, 50th (median), and 75th percentile values
    for the longer-run target federal funds rate question.
    
    Output is a tidy CSV with one row per survey date per panel.
    """
    # Configure logging
    if verbose:
        import logging
        logging.getLogger("nyfed_extractor").setLevel(logging.DEBUG)
    
    # Handle OCR flags
    ocr_enabled = use_ocr and not no_ocr
    
    logger.info("=" * 60)
    logger.info("NY Fed Longer-Run Federal Funds Rate Extractor")
    logger.info("=" * 60)
    logger.info(f"Year range: {start_year} - {end_year}")
    logger.info(f"Data directory: {data_dir}")
    logger.info(f"Output: {output_dir / output_file}")
    logger.info(f"OCR enabled: {ocr_enabled}")
    
    # Ensure directories exist
    data_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Step 1: Scrape manifest
    logger.info("\n[1/4] Scraping survey manifest...")
    try:
        meetings = scrape_manifest(
            start_year=start_year,
            end_year=end_year,
        )
    except Exception as e:
        logger.error(f"Failed to scrape manifest: {e}")
        raise click.ClickException(f"Manifest scraping failed: {e}")
    
    if not meetings:
        logger.warning("No meetings found in the specified year range")
        raise click.ClickException("No survey meetings found")
    
    logger.info(f"Found {len(meetings)} meetings with survey data")
    
    # Step 2: Download files
    if not skip_download:
        logger.info("\n[2/4] Downloading survey files...")
        try:
            downloaded = download_all_meetings(
                meetings=meetings,
                data_dir=data_dir,
                prefer_xlsx=True,
                force=redownload,
                max_files=max_files,
            )
            logger.info(f"Downloaded {len(downloaded)} files")
        except Exception as e:
            logger.error(f"Download failed: {e}")
            raise click.ClickException(f"Download failed: {e}")
    else:
        logger.info("\n[2/4] Skipping download (using existing files)")
    
    # Step 3: Extract percentiles
    logger.info("\n[3/4] Extracting percentiles from files...")
    all_results: List[ExtractedPercentile] = []
    
    for meeting in tqdm(meetings, desc="Processing", unit="meeting"):
        try:
            results = process_meeting(
                meeting=meeting,
                data_dir=data_dir,
                use_ocr=ocr_enabled,
            )
            all_results.extend(results)
        except Exception as e:
            logger.error(f"Failed to process {meeting.meeting_label}: {e}")
            # Add error placeholder
            all_results.append(ExtractedPercentile(
                survey_date=meeting.meeting_date,
                panel=PANEL_COMBINED,
                concept=CONCEPT_FF_LONGER_RUN,
                pctl25=None,
                pctl50=None,
                pctl75=None,
                source="",
                file_url="",
                local_path="",
                notes=f"processing_error: {str(e)[:100]}",
            ))
    
    logger.info(f"Extracted {len(all_results)} total records")
    
    # Step 4: Write output
    logger.info("\n[4/4] Writing output CSV...")
    output_path = output_dir / output_file
    
    # Sort results by date (newest first), then by panel
    all_results.sort(key=lambda r: (r.survey_date, r.panel), reverse=True)
    
    try:
        write_csv(all_results, output_path)
    except Exception as e:
        logger.error(f"Failed to write CSV: {e}")
        raise click.ClickException(f"CSV write failed: {e}")
    
    # Summary
    logger.info("\n" + "=" * 60)
    logger.info("EXTRACTION COMPLETE")
    logger.info("=" * 60)
    logger.info(f"Total records: {len(all_results)}")
    
    # Count by source
    source_counts = {}
    for r in all_results:
        source_counts[r.source] = source_counts.get(r.source, 0) + 1
    logger.info("Records by source:")
    for source, count in sorted(source_counts.items()):
        logger.info(f"  {source}: {count}")
    
    # Count missing
    missing = sum(1 for r in all_results if r.pctl50 is None)
    logger.info(f"Records with missing median: {missing}")
    
    logger.info(f"\nOutput file: {output_path.absolute()}")


if __name__ == "__main__":
    main()

