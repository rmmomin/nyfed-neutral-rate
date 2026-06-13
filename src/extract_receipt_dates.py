"""
Extract survey distribution and receipt deadline metadata from NY Fed PDFs.

Most survey result PDFs include a header like:
Distributed: 01/14/2026 - Received by: 01/20/2026
"""

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict

import pdfplumber

from .utils import PANEL_COMBINED, PANEL_SMP, PANEL_SPD, logger


MONTH_MAP = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}

RECEIPT_RE = re.compile(
    r"Distributed:\s*(?P<distributed>\d{1,2}/\d{1,2}/\d{2,4})"
    r"\s*[-–—]\s*Received\s+by:\s*(?P<received>\d{1,2}/\d{1,2}/\d{2,4})",
    re.IGNORECASE,
)

# These May 2023 PDFs have image-only cover pages, so pdfplumber cannot read the
# header text. The rendered covers show the same header in both documents:
# Distributed: 4/19/2023 - Received by: 4/24/2023.
IMAGE_ONLY_COVER_OVERRIDES = {
    "may-2023-smp-results.pdf": ("2023-05-01", PANEL_SMP, "2023-04-19", "2023-04-24"),
    "may-2023-spd-results.pdf": ("2023-05-01", PANEL_SPD, "2023-04-19", "2023-04-24"),
}


@dataclass
class SurveyReceiptDates:
    """Distribution and receipt deadline metadata for a survey document."""

    survey_date: Optional[datetime]
    panel: str
    distributed_date: Optional[datetime]
    received_by_date: Optional[datetime]
    source_file: str
    notes: Optional[str] = None

    def to_dict(self) -> Dict[str, Optional[str]]:
        return {
            "survey_date": self.survey_date.strftime("%Y-%m-%d") if self.survey_date else None,
            "panel": self.panel,
            "distributed_date": self.distributed_date.strftime("%Y-%m-%d") if self.distributed_date else None,
            "received_by_date": self.received_by_date.strftime("%Y-%m-%d") if self.received_by_date else None,
            "source_file": self.source_file,
            "notes": self.notes,
        }


def parse_mmddyyyy(value: str) -> Optional[datetime]:
    """Parse M/D/YYYY or MM/DD/YY style dates."""
    value = value.strip()
    for fmt in ("%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def parse_survey_date_from_filename(filename: str) -> Optional[datetime]:
    """Infer the survey month from a local PDF filename."""
    filename_lower = filename.lower()
    year_match = re.search(r"20\d{2}", filename_lower)
    if not year_match:
        return None

    month_matches = []
    for month_name, month_num in MONTH_MAP.items():
        for match in re.finditer(rf"(?<![a-z]){re.escape(month_name)}(?![a-z])", filename_lower):
            month_matches.append((match.start(), month_num))

    if not month_matches:
        return None

    before_year = [item for item in month_matches if item[0] < year_match.start()]
    if before_year:
        month = sorted(before_year)[-1][1]
    else:
        month = sorted(month_matches)[0][1]

    return datetime(int(year_match.group()), month, 1)


def infer_panel(filename: str, text: str, survey_date: Optional[datetime]) -> str:
    """Infer SPD/SMP/Combined panel from filename and document text."""
    filename_lower = filename.lower()
    text_lower = text.lower()

    if "sme" in filename_lower:
        return PANEL_COMBINED
    if "smp" in filename_lower or "participant" in filename_lower:
        return PANEL_SMP
    if (
        filename_lower.startswith("mp-")
        or filename_lower.startswith("mp_")
        or "-mp" in filename_lower
        or "_mp" in filename_lower
    ):
        return PANEL_SMP
    if "spd" in filename_lower or "dealer" in filename_lower:
        return PANEL_SPD

    if "survey of market participants" in text_lower:
        return PANEL_SMP
    if "survey of primary dealers" in text_lower:
        return PANEL_SPD

    if survey_date and survey_date < datetime(2014, 1, 1):
        return PANEL_SPD

    return PANEL_COMBINED


def extract_text_head(filepath: Path, max_pages: int = 2) -> str:
    """Extract text from the first pages of a PDF."""
    with pdfplumber.open(filepath) as pdf:
        parts = []
        for page in pdf.pages[:max_pages]:
            parts.append(page.extract_text() or "")
    return "\n".join(parts)


def extract_receipt_dates_from_pdf(filepath: Path) -> SurveyReceiptDates:
    """Extract receipt metadata from a single PDF."""
    try:
        text = extract_text_head(filepath)
    except Exception as exc:
        logger.warning(f"Could not read {filepath}: {exc}")
        return SurveyReceiptDates(
            survey_date=parse_survey_date_from_filename(filepath.name),
            panel=PANEL_COMBINED,
            distributed_date=None,
            received_by_date=None,
            source_file=str(filepath),
            notes=f"pdf_read_error: {exc}",
        )

    override = IMAGE_ONLY_COVER_OVERRIDES.get(filepath.name.lower())
    if override:
        survey_date, panel, distributed_date, received_by_date = override
        return SurveyReceiptDates(
            survey_date=datetime.fromisoformat(survey_date),
            panel=panel,
            distributed_date=datetime.fromisoformat(distributed_date),
            received_by_date=datetime.fromisoformat(received_by_date),
            source_file=str(filepath),
            notes="image_only_cover_manual",
        )

    match = RECEIPT_RE.search(text.replace("\u2011", "-"))
    distributed_date = parse_mmddyyyy(match.group("distributed")) if match else None
    received_by_date = parse_mmddyyyy(match.group("received")) if match else None

    survey_date = parse_survey_date_from_filename(filepath.name)
    if not survey_date and distributed_date:
        survey_date = datetime(distributed_date.year, distributed_date.month, 1)

    panel = infer_panel(filepath.name, text, survey_date)
    notes = None if match else "receipt_dates_not_found"

    return SurveyReceiptDates(
        survey_date=survey_date,
        panel=panel,
        distributed_date=distributed_date,
        received_by_date=received_by_date,
        source_file=str(filepath),
        notes=notes,
    )


def deduplicate_receipt_dates(records: List[SurveyReceiptDates]) -> List[SurveyReceiptDates]:
    """Collapse multiple local files for the same survey date/panel."""
    found = [r for r in records if r.survey_date and r.received_by_date]
    grouped: Dict[tuple, List[SurveyReceiptDates]] = {}
    for record in found:
        grouped.setdefault((record.survey_date, record.panel), []).append(record)

    deduped = []
    for (survey_date, panel), group in grouped.items():
        # Prefer files whose names include the survey year, then shorter local names.
        group = sorted(
            group,
            key=lambda r: (
                str(survey_date.year) not in Path(r.source_file).name,
                len(Path(r.source_file).name),
                Path(r.source_file).name.lower(),
            ),
        )
        chosen = group[0]
        distributed_values = sorted({r.distributed_date.strftime("%Y-%m-%d") for r in group if r.distributed_date})
        received_values = sorted({r.received_by_date.strftime("%Y-%m-%d") for r in group if r.received_by_date})

        if len(distributed_values) > 1 or len(received_values) > 1:
            chosen.notes = (
                f"conflicting_duplicates: distributed={';'.join(distributed_values)}, "
                f"received_by={';'.join(received_values)}"
            )

        deduped.append(chosen)

    return sorted(deduped, key=lambda r: (r.survey_date, r.panel))


def extract_receipt_dates_from_dir(data_dir: Path) -> List[SurveyReceiptDates]:
    """Extract and deduplicate receipt metadata from all PDFs in data_dir."""
    records = [extract_receipt_dates_from_pdf(path) for path in sorted(data_dir.glob("*.pdf"))]
    return deduplicate_receipt_dates(records)
