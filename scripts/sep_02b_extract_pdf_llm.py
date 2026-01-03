#!/usr/bin/env python3
"""
Extract SEP dot plot data from PDFs using OpenAI API.

Sends entire PDF files directly to OpenAI API for Figure 2 extraction.

Usage:
    export OPENAI_API_KEY="your-key"
    python scripts/sep_02b_extract_pdf_llm.py
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
from typing import Optional, Dict, List

from tqdm import tqdm
from openai import OpenAI


# Configuration
MODEL = "gpt-4o"  # Using gpt-4o for vision capabilities
SOURCE = "sep_pdf"
RATE_LIMIT_DELAY = 3.0  # seconds between API calls (increased for rate limits)
API_TIMEOUT = 120  # seconds
MAX_RETRIES = 3  # Number of retries on rate limit errors


def get_client() -> Optional[OpenAI]:
    """Get OpenAI client from environment variable."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("ERROR: OPENAI_API_KEY not set!")
        return None
    return OpenAI(api_key=api_key, timeout=API_TIMEOUT)


def call_llm_with_pdf(client: OpenAI, filepath: Path) -> Dict:
    """Call LLM with entire PDF file to extract Figure 2 dot plot data."""

    # Read PDF as base64
    with open(filepath, "rb") as f:
        pdf_base64 = base64.standard_b64encode(f.read()).decode("utf-8")

    prompt = """Analyze this FOMC Summary of Economic Projections (SEP) PDF.

Find Figure 2 which shows the federal funds rate dot plot - a scatter plot showing
individual FOMC participant projections for the federal funds rate.

For the "Longer run" column (rightmost column in the dot plot), count the number
of dots at each rate level. The dots represent individual participant projections.

Rate levels are typically spaced at 0.25% intervals (e.g., 2.00, 2.25, 2.50, 2.75, 3.00, etc.)

IMPORTANT: Count ONLY the "Longer run" column dots, not other year columns.

Return ONLY valid JSON (no markdown, no code blocks):
{
  "meeting_date": "March 2014",
  "found": true,
  "longer_run_dots": {
    "3.50": 2,
    "3.75": 5,
    "4.00": 8,
    "4.25": 2
  },
  "total_participants": 17,
  "page": 2
}

The keys in longer_run_dots should be rate levels as strings (e.g., "3.75"),
and values should be the count of dots at that level.

If Figure 2 is NOT found or you cannot count the dots:
{"meeting_date": "March 2014", "found": false, "reason": "explanation here"}"""

    for attempt in range(MAX_RETRIES):
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
                max_completion_tokens=1000,
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
            print(f"  JSON parse error for {filepath.name}: {e}")
            return {"found": False, "error": "json_parse_error", "raw": content[:200] if 'content' in dir() else ""}
        except Exception as e:
            error_str = str(e)
            if "429" in error_str or "rate_limit" in error_str.lower():
                wait_time = (attempt + 1) * 5  # Exponential backoff: 5, 10, 15 seconds
                print(f"  Rate limited, waiting {wait_time}s (attempt {attempt + 1}/{MAX_RETRIES})...")
                time.sleep(wait_time)
                continue
            print(f"  LLM call failed for {filepath.name}: {e}")
            return {"found": False, "error": str(e)[:100]}

    print(f"  Max retries exceeded for {filepath.name}")
    return {"found": False, "error": "max_retries_exceeded"}


def parse_meeting_date(result: Dict, filename: str) -> datetime:
    """Parse meeting date from LLM result or filename."""
    MONTHS = {
        'january': 1, 'february': 2, 'march': 3, 'april': 4, 'may': 5, 'june': 6,
        'july': 7, 'august': 8, 'september': 9, 'october': 10, 'november': 11, 'december': 12,
        'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'jun': 6, 'jul': 7,
        'aug': 8, 'sep': 9, 'sept': 9, 'oct': 10, 'nov': 11, 'dec': 12
    }

    # Try LLM-extracted date
    meeting_str = result.get("meeting_date", "").lower()
    if meeting_str:
        for month_name, month_num in MONTHS.items():
            if month_name in meeting_str:
                year_match = re.search(r'20\d{2}', result.get("meeting_date", ""))
                if year_match:
                    return datetime(int(year_match.group()), month_num, 1)

    # Fallback: parse from filename (e.g., FOMC20140319SEPcompilation.pdf)
    date_match = re.search(r'FOMC(\d{8})', filename, re.I)
    if date_match:
        date_str = date_match.group(1)
        return datetime.strptime(date_str, "%Y%m%d")

    # Last resort
    year_match = re.search(r'20\d{2}', filename)
    if year_match:
        return datetime(int(year_match.group()), 1, 1)

    return datetime.now()


def dots_to_percentiles(longer_run_dots: Dict[str, int]) -> Dict[str, float]:
    """Convert dot counts to percentiles (p25, p50, p75)."""
    import numpy as np

    if not longer_run_dots:
        return {"n": 0, "p25": None, "p50": None, "p75": None}

    # Expand dots to individual values
    values = []
    for rate_str, count in longer_run_dots.items():
        try:
            rate = float(rate_str)
            values.extend([rate] * int(count))
        except (ValueError, TypeError):
            continue

    if not values:
        return {"n": 0, "p25": None, "p50": None, "p75": None}

    return {
        "n": len(values),
        "p25": float(np.quantile(values, 0.25)),
        "p50": float(np.quantile(values, 0.50)),
        "p75": float(np.quantile(values, 0.75)),
    }


def process_pdf(filepath: Path, client: OpenAI) -> Optional[Dict]:
    """Process a single PDF file and return extracted data."""

    result = call_llm_with_pdf(client, filepath)
    time.sleep(RATE_LIMIT_DELAY)

    meeting_date = parse_meeting_date(result, filepath.name)

    if not result.get("found"):
        return {
            "meeting_date": meeting_date.strftime("%Y-%m-%d"),
            "horizon": "Longer run",
            "n": None,
            "p25": None,
            "p50": None,
            "p75": None,
            "source": SOURCE,
            "file_path": str(filepath),
            "page": None,
            "notes": result.get("reason") or result.get("error"),
        }

    # Convert dots to percentiles
    dots = result.get("longer_run_dots", {})
    percentiles = dots_to_percentiles(dots)

    return {
        "meeting_date": meeting_date.strftime("%Y-%m-%d"),
        "horizon": "Longer run",
        "n": percentiles["n"],
        "p25": percentiles["p25"],
        "p50": percentiles["p50"],
        "p75": percentiles["p75"],
        "source": SOURCE,
        "file_path": str(filepath),
        "page": result.get("page"),
        "notes": None,
    }


def main():
    data_dir = Path("data_raw/sep")
    output_path = Path("data_out/sep_pdf_extracts.csv")

    if not data_dir.exists():
        print(f"Error: {data_dir} not found. Run sep_01b_download_pdfs.py first.")
        return

    print("=" * 60)
    print("SEP PDF Extraction using OpenAI API")
    print(f"Model: {MODEL}")
    print("=" * 60)

    client = get_client()
    if not client:
        sys.exit(1)

    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Find PDF files
    pdf_files = sorted(data_dir.glob("*.pdf"))
    print(f"Found {len(pdf_files)} PDF files")

    if not pdf_files:
        print("No PDF files found. Run sep_01b_download_pdfs.py first.")
        return

    results = []

    for filepath in tqdm(pdf_files, desc="Processing PDFs"):
        result = process_pdf(filepath, client)
        if result:
            results.append(result)
            if result.get("p50"):
                print(f"  {filepath.name}: median={result['p50']:.2f}%")

    # Write CSV
    print(f"\nWriting {len(results)} records to {output_path}")

    with open(output_path, "w", newline="") as f:
        fieldnames = ["meeting_date", "horizon", "n", "p25", "p50", "p75", "source", "file_path", "page", "notes"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in results:
            writer.writerow(r)

    # Summary
    valid_count = sum(1 for r in results if r.get("p50") is not None)
    print("=" * 60)
    print("EXTRACTION COMPLETE")
    print(f"  Total PDFs: {len(pdf_files)}")
    print(f"  Processed: {len(results)}")
    print(f"  Valid (has median): {valid_count}")
    print(f"  Output: {output_path}")
    print("=" * 60)


if __name__ == "__main__":
    main()
