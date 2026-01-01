#!/usr/bin/env python3
"""
Step 3: Extract percentiles from PDF files using LLM (gpt-5.2).

Sends entire PDF files directly to OpenAI API (not extracted text).

Usage:
    export OPENAI_API_KEY="your-key"
    python scripts/03_extract_pdf_llm.py
"""

import base64
import csv
import json
import os
import re
import sys
import time
from pathlib import Path
from datetime import datetime
from typing import Optional, Set

sys.path.insert(0, str(Path(__file__).parent.parent))

import click
from tqdm import tqdm
from openai import OpenAI

from src.utils import (
    logger,
    CONCEPT_FF_LONGER_RUN,
    PANEL_SPD,
    PANEL_SMP,
    PANEL_COMBINED,
    ExtractedPercentile,
)


# Configuration
MODEL = "gpt-5.2"
SOURCE = "pdf_llm"
RATE_LIMIT_DELAY = 0.5  # seconds between API calls
API_TIMEOUT = 120  # seconds (increased for PDF processing)


def get_client() -> Optional[OpenAI]:
    """Get OpenAI client from environment."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        logger.error("OPENAI_API_KEY not set!")
        return None
    return OpenAI(api_key=api_key, timeout=API_TIMEOUT)


def determine_panel(filename: str, survey_date: datetime = None) -> str:
    """Determine panel type from filename and date.
    
    Note: SMP (Survey of Market Participants) started in January 2014.
    File naming conventions:
    - 2014-2015: "mp_" prefix for Market Participants
    - 2016+: "smp" or "SMP" in filename
    """
    fn = filename.lower()
    
    # Check for SPD markers
    if 'spd' in fn or 'dealer' in fn:
        return PANEL_SPD
    
    # Check for SMP markers (includes "mp_" and "mp" patterns used in 2014-2016)
    # Patterns: smp, participant, mp-, -mp_, mp_, -mp.pdf, -results-mp.pdf
    if 'smp' in fn or 'participant' in fn or fn.startswith('mp-') or '-mp_' in fn or fn.startswith('mp_') or '-mp.pdf' in fn or '-results-mp' in fn:
        return PANEL_SMP
    
    # For dates before January 2014, only SPD existed
    # If no explicit panel marker and before SMP launch, it's SPD
    if survey_date and survey_date < datetime(2014, 1, 1):
        return PANEL_SPD
    
    # For dates between Jan 2014 and Nov 2016 without markers, assume SPD
    # (the primary dealer survey, as SMP files have mp_ prefix)
    if survey_date and survey_date < datetime(2016, 11, 1):
        return PANEL_SPD
    
    return PANEL_COMBINED


def get_xlsx_dates(xlsx_csv: Path) -> Set[str]:
    """Get set of dates that have XLSX data (YYYY-MM format)."""
    dates = set()
    if xlsx_csv.exists():
        with open(xlsx_csv) as f:
            reader = csv.DictReader(f)
            for row in reader:
                date_str = row.get("survey_date", "")
                if date_str and len(date_str) >= 7:
                    # Extract YYYY-MM
                    dates.add(date_str[:7])
    return dates


def call_llm_with_pdf(client: OpenAI, filepath: Path) -> dict:
    """Call LLM with entire PDF file (not extracted text)."""
    
    # Read PDF as base64
    with open(filepath, "rb") as f:
        pdf_base64 = base64.standard_b64encode(f.read()).decode("utf-8")
    
    prompt = """Analyze this NY Federal Reserve survey PDF and extract:

1. The survey date (month and year) - look at the title/header
2. The "Longer Run" federal funds rate target percentiles

CRITICAL - THERE ARE TWO SIMILAR COLUMNS IN THE TABLE:
- "Longer Run" column - EXTRACT FROM THIS ONE (typically higher values: 2.5-4.0%)
- "10-yr Average FF Rate" column - DO NOT USE THIS (typically lower values)

Look at the column HEADERS carefully. Extract values from the "Longer Run" column ONLY.

Extract these percentiles from the "Longer Run" column:
- 25th Percentile (25th Pctl)
- Median (50th Percentile)
- 75th Percentile (75th Pctl)

Return ONLY valid JSON (no markdown):
{"survey_month": "July", "survey_year": 2017, "found": true, "pctl25": 2.50, "pctl50": 2.75, "pctl75": 3.00, "page": 4}

If the longer-run question is NOT in this PDF:
{"survey_month": "July", "survey_year": 2017, "found": false, "pctl25": null, "pctl50": null, "pctl75": null, "page": null, "reason": "question not present"}"""

    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "file",
                            "file": {
                                "filename": filepath.name,
                                "file_data": f"data:application/pdf;base64,{pdf_base64}",
                            }
                        },
                        {
                            "type": "text",
                            "text": prompt
                        }
                    ],
                }
            ],
            max_completion_tokens=200,
            temperature=0,
        )
        
        content = response.choices[0].message.content.strip()
        
        # Clean markdown if present
        if content.startswith("```"):
            lines = content.split("\n")
            content = "\n".join(lines[1:-1] if lines[-1].startswith("```") else lines[1:])
            content = content.strip()
        
        return json.loads(content)
        
    except json.JSONDecodeError as e:
        logger.warning(f"JSON parse error for {filepath.name}: {e}")
        return {"found": False, "error": "json_parse_error"}
    except Exception as e:
        logger.error(f"LLM call failed for {filepath.name}: {e}")
        return {"found": False, "error": str(e)[:100]}


def parse_survey_date(result: dict, filename: str) -> datetime:
    """Parse survey date from LLM result or filename."""
    MONTHS = {
        'january': 1, 'february': 2, 'march': 3, 'april': 4, 'may': 5, 'june': 6,
        'july': 7, 'august': 8, 'september': 9, 'october': 10, 'november': 11, 'december': 12,
        'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'jun': 6, 'jul': 7,
        'aug': 8, 'sep': 9, 'sept': 9, 'oct': 10, 'nov': 11, 'dec': 12
    }
    
    # Try LLM-extracted date
    month_str = result.get("survey_month", "").lower()
    year = result.get("survey_year")
    
    if month_str and year:
        month = MONTHS.get(month_str)
        if month and isinstance(year, int) and 2010 <= year <= 2030:
            return datetime(year, month, 1)
    
    # Fallback: parse from filename
    fn = filename.lower()
    for month_name, month_num in MONTHS.items():
        if month_name in fn:
            year_match = re.search(r'20\d{2}', filename)
            if year_match:
                return datetime(int(year_match.group()), month_num, 1)
    
    # Last resort
    year_match = re.search(r'20\d{2}', filename)
    if year_match:
        return datetime(int(year_match.group()), 1, 1)
    
    return datetime.now()


def process_pdf(filepath: Path, client: OpenAI, xlsx_dates: Set[str]) -> Optional[ExtractedPercentile]:
    """Process a single PDF file."""
    
    # Call LLM with entire PDF
    result = call_llm_with_pdf(client, filepath)
    
    # Rate limit
    time.sleep(RATE_LIMIT_DELAY)
    
    # Parse date from LLM result
    survey_date = parse_survey_date(result, filepath.name)
    
    # Determine panel based on filename and date
    panel = determine_panel(filepath.name, survey_date)
    
    # Check if we already have XLSX data for this date
    date_key = survey_date.strftime("%Y-%m")
    if date_key in xlsx_dates:
        logger.debug(f"Skipping {filepath.name} - XLSX exists for {date_key}")
        return None  # Skip - XLSX takes priority
    
    # Validate values
    pctl25 = result.get("pctl25")
    pctl50 = result.get("pctl50")
    pctl75 = result.get("pctl75")
    
    # Sanity check - rates should be between 0 and 10%
    if pctl25 is not None and (pctl25 < 0 or pctl25 > 10):
        pctl25 = None
    if pctl50 is not None and (pctl50 < 0 or pctl50 > 10):
        pctl50 = None
    if pctl75 is not None and (pctl75 < 0 or pctl75 > 10):
        pctl75 = None
    
    notes = result.get("reason") or result.get("error") if not result.get("found") else None
    
    return ExtractedPercentile(
        survey_date=survey_date,
        panel=panel,
        concept=CONCEPT_FF_LONGER_RUN,
        pctl25=pctl25,
        pctl50=pctl50,
        pctl75=pctl75,
        source=SOURCE,
        file_url=str(filepath),
        local_path=str(filepath),
        pdf_page=result.get("page"),
        notes=notes,
    )


@click.command()
@click.option("--data-dir", default="data_raw", type=click.Path(path_type=Path, exists=True))
@click.option("--xlsx-csv", default="data_out/xlsx_extracts.csv", type=click.Path(path_type=Path))
@click.option("--output", default="data_out/pdf_extracts.csv", type=click.Path(path_type=Path))
@click.option("--limit", default=None, type=int, help="Limit number of PDFs to process")
def main(data_dir: Path, xlsx_csv: Path, output: Path, limit: Optional[int]):
    """Extract percentiles from PDFs using LLM with direct PDF upload."""
    
    logger.info("=" * 60)
    logger.info("Step 3: Extract Data from PDFs using LLM")
    logger.info(f"Model: {MODEL}")
    logger.info("Method: Direct PDF upload (not text extraction)")
    logger.info("=" * 60)
    
    client = get_client()
    if not client:
        logger.error("Cannot proceed without OPENAI_API_KEY")
        sys.exit(1)
    
    output.parent.mkdir(parents=True, exist_ok=True)
    
    # Load XLSX dates to skip duplicates
    xlsx_dates = get_xlsx_dates(xlsx_csv)
    logger.info(f"Found {len(xlsx_dates)} dates with XLSX data (will skip matching PDFs)")
    
    # Find PDF files
    pdf_files = sorted(data_dir.glob("*.pdf"))
    logger.info(f"Found {len(pdf_files)} PDF files")
    
    if limit:
        pdf_files = pdf_files[:limit]
        logger.info(f"Limited to {limit} files")
    
    results = []
    skipped = 0
    
    for filepath in tqdm(pdf_files, desc="Processing PDFs"):
        result = process_pdf(filepath, client, xlsx_dates)
        if result is None:
            skipped += 1
        else:
            results.append(result)
            if result.pctl50:
                logger.debug(f"{filepath.name}: {result.survey_date.strftime('%Y-%m')} median={result.pctl50}")
    
    # Write CSV
    logger.info(f"Writing {len(results)} records to {output}")
    
    with open(output, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "survey_date", "panel", "concept", "pctl25", "pctl50", "pctl75",
            "source", "file_url", "local_path", "pdf_page", "notes"
        ])
        writer.writeheader()
        for r in results:
            writer.writerow(r.to_dict())
    
    # Summary
    valid_count = sum(1 for r in results if r.pctl50 is not None)
    logger.info("=" * 60)
    logger.info("PDF EXTRACTION COMPLETE")
    logger.info(f"  Total PDFs: {len(pdf_files)}")
    logger.info(f"  Skipped (XLSX exists): {skipped}")
    logger.info(f"  Processed: {len(results)}")
    logger.info(f"  Valid (has median): {valid_count}")
    logger.info(f"  Output: {output.absolute()}")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
