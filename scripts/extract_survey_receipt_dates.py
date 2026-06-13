#!/usr/bin/env python3
"""
Extract NY Fed survey distribution and receipt deadline dates from result PDFs.

Usage:
    python scripts/extract_survey_receipt_dates.py
"""

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import click

from src.extract_receipt_dates import extract_receipt_dates_from_dir
from src.utils import logger


FIELDNAMES = [
    "survey_date",
    "panel",
    "distributed_date",
    "received_by_date",
    "source_file",
    "notes",
]


@click.command()
@click.option("--data-dir", default="data_raw", type=click.Path(path_type=Path, exists=True))
@click.option("--output", default="data_out/nyfed_survey_receipt_dates.csv", type=click.Path(path_type=Path))
def main(data_dir: Path, output: Path):
    """Extract receipt dates from survey result PDFs."""
    logger.info("=" * 60)
    logger.info("Extract Survey Receipt Dates")
    logger.info("=" * 60)

    output.parent.mkdir(parents=True, exist_ok=True)

    records = extract_receipt_dates_from_dir(data_dir)

    with open(output, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES, lineterminator="\n")
        writer.writeheader()
        for record in records:
            writer.writerow(record.to_dict())

    valid_count = sum(1 for record in records if record.received_by_date is not None)
    logger.info(f"Wrote {len(records)} deduplicated records to {output}")
    logger.info(f"Records with received_by_date: {valid_count}")
    if records:
        logger.info(
            "Date range: %s to %s",
            records[0].survey_date.strftime("%Y-%m-%d"),
            records[-1].survey_date.strftime("%Y-%m-%d"),
        )


if __name__ == "__main__":
    main()
