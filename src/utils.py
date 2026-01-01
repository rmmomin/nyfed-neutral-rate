"""Common utilities, constants, and data structures for the NY Fed survey extractor."""

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("nyfed_extractor")


# Base URL for NY Fed surveys
NYFED_BASE_URL = "https://www.newyorkfed.org"
SURVEY_PAGE_URL = f"{NYFED_BASE_URL}/markets/market-intelligence/survey-of-market-expectations"

# Panel types
PANEL_SPD = "SPD"  # Survey of Primary Dealers
PANEL_SMP = "SMP"  # Survey of Market Participants
PANEL_DEALER = "Dealer"
PANEL_PARTICIPANT = "Participant"
PANEL_COMBINED = "Combined"
PANEL_MERGED = "Merged"  # Post-2025 merged survey

# Source types
SOURCE_XLSX = "xlsx"
SOURCE_PDF_TEXT = "pdf_text"
SOURCE_PDF_OCR = "pdf_ocr"

# Concept identifier
CONCEPT_FF_LONGER_RUN = "ff_longer_run_target"

# Keywords for matching longer-run federal funds rate
LONGER_RUN_KEYWORDS = [
    r"longer[\s-]*run",
    r"long[\s-]*run",
    r"longrun",
]
FEDERAL_FUNDS_KEYWORDS = [
    r"federal\s*funds",
    r"fed\s*funds",
    r"fftr",
    r"target\s*rate",
]

# XLSX value tag for the concept
XLSX_VALUE_TAG = "fftr_modalpe_longerrun"

# Percentile row patterns
PERCENTILE_PATTERNS = {
    "pctl25": [r"25th\s*p(?:e?r)?c?t?l?", r"25\s*percentile", r"p25", r"pctl_?25"],
    "pctl50": [r"median", r"50th\s*p(?:e?r)?c?t?l?", r"50\s*percentile", r"p50", r"pctl_?50"],
    "pctl75": [r"75th\s*p(?:e?r)?c?t?l?", r"75\s*percentile", r"p75", r"pctl_?75"],
}


@dataclass
class SurveyLink:
    """Represents a link to a survey file (XLSX or PDF)."""
    url: str
    file_type: str  # "xlsx" or "pdf"
    survey_type: str  # "SPD", "SMP", or "merged"
    link_text: str
    is_data_file: bool = False  # True if it's a "Data" XLSX file
    is_results_pdf: bool = False  # True if it's a "Results" PDF


@dataclass
class SurveyMeeting:
    """Represents a survey meeting date with associated files."""
    meeting_date: datetime
    meeting_label: str  # Original label from the page (e.g., "January 2025 FOMC")
    year: int
    links: List[SurveyLink] = field(default_factory=list)
    
    def get_xlsx_links(self) -> List[SurveyLink]:
        """Get all XLSX data links for this meeting."""
        return [l for l in self.links if l.file_type == "xlsx" and l.is_data_file]
    
    def get_pdf_links(self) -> List[SurveyLink]:
        """Get all PDF results links for this meeting."""
        return [l for l in self.links if l.file_type == "pdf" and l.is_results_pdf]


@dataclass
class ExtractedPercentile:
    """Represents extracted percentile data for a survey."""
    survey_date: datetime
    panel: str
    concept: str
    pctl25: Optional[float]
    pctl50: Optional[float]
    pctl75: Optional[float]
    source: str
    file_url: str
    local_path: str
    pdf_page: Optional[int] = None
    notes: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for CSV output."""
        return {
            "survey_date": self.survey_date.strftime("%Y-%m-%d"),
            "panel": self.panel,
            "concept": self.concept,
            "pctl25": self.pctl25,
            "pctl50": self.pctl50,
            "pctl75": self.pctl75,
            "source": self.source,
            "file_url": self.file_url,
            "local_path": self.local_path,
            "pdf_page": self.pdf_page,
            "notes": self.notes,
        }


def matches_longer_run_ff(text: str) -> bool:
    """Check if text matches longer-run federal funds rate keywords."""
    text_lower = text.lower()
    
    # Check for longer-run keyword
    has_longer_run = any(
        re.search(pattern, text_lower, re.IGNORECASE)
        for pattern in LONGER_RUN_KEYWORDS
    )
    
    # Check for federal funds keyword
    has_ff = any(
        re.search(pattern, text_lower, re.IGNORECASE)
        for pattern in FEDERAL_FUNDS_KEYWORDS
    )
    
    return has_longer_run and has_ff


def normalize_percent(value: Any) -> Optional[float]:
    """
    Normalize a value to percent format.
    
    Handles:
    - Already in percent (e.g., 3.13)
    - In decimal form (e.g., 0.0313)
    - String with % sign
    """
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    
    if isinstance(value, str):
        # Remove % sign and whitespace
        value = value.strip().replace("%", "").strip()
        if not value or value.lower() in ("na", "n/a", "-", ""):
            return None
        try:
            value = float(value)
        except ValueError:
            return None
    
    if not isinstance(value, (int, float)):
        return None
    
    # If value is less than 1, assume it's in decimal form (e.g., 0.0313 = 3.13%)
    # Fed funds rate is typically between 0-15%, so decimal form would be < 0.15
    if abs(value) < 0.5:
        value = value * 100
    
    return round(value, 4)


def parse_date_from_label(label: str) -> Optional[datetime]:
    """
    Parse a meeting date from a label like "January 2025 FOMC" or "Jul/Aug 2024".
    
    Returns the first day of the month as the date.
    """
    label = label.strip()
    
    # Month name patterns
    month_patterns = [
        r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})",
        r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)(?:/\w+)?\s+(\d{4})",
        r"(\d{1,2})/(\d{4})",  # MM/YYYY format
    ]
    
    month_map = {
        "january": 1, "february": 2, "march": 3, "april": 4,
        "may": 5, "june": 6, "july": 7, "august": 8,
        "september": 9, "october": 10, "november": 11, "december": 12,
        "jan": 1, "feb": 2, "mar": 3, "apr": 4,
        "jun": 6, "jul": 7, "aug": 8, "sep": 9,
        "oct": 10, "nov": 11, "dec": 12,
    }
    
    for pattern in month_patterns[:2]:
        match = re.search(pattern, label, re.IGNORECASE)
        if match:
            month_str = match.group(1).lower()
            year = int(match.group(2))
            month = month_map.get(month_str)
            if month:
                return datetime(year, month, 1)
    
    # Try MM/YYYY pattern
    match = re.search(month_patterns[2], label)
    if match:
        month = int(match.group(1))
        year = int(match.group(2))
        if 1 <= month <= 12:
            return datetime(year, month, 1)
    
    return None


def classify_survey_link(url: str, link_text: str) -> Optional[SurveyLink]:
    """
    Classify a link as SPD, SMP, or merged survey, and determine if it's data or results.
    
    Returns None if the link is not relevant (e.g., press releases, not survey data).
    """
    url_lower = url.lower()
    text_lower = link_text.lower()
    
    # Determine file type
    if url_lower.endswith(".xlsx") or url_lower.endswith(".xls"):
        file_type = "xlsx"
    elif url_lower.endswith(".pdf"):
        file_type = "pdf"
    else:
        return None
    
    # Classify survey type
    survey_type = None
    is_data_file = False
    is_results_pdf = False
    
    # Check for SPD (Survey of Primary Dealers)
    if "spd" in url_lower or "primary" in text_lower or "dealer" in text_lower:
        survey_type = PANEL_SPD
    # Check for SMP (Survey of Market Participants)
    elif "smp" in url_lower or "participant" in text_lower:
        survey_type = PANEL_SMP
    # Check for merged survey (2025+)
    elif "sme" in url_lower or "market-expectations" in url_lower or "merged" in text_lower:
        survey_type = PANEL_MERGED
    # Try to infer from context
    elif file_type == "xlsx" and "data" in text_lower:
        survey_type = PANEL_MERGED  # Assume merged if can't determine
    elif file_type == "pdf" and "result" in text_lower:
        survey_type = PANEL_MERGED
    
    if survey_type is None:
        return None
    
    # Determine if it's a data file or results
    if file_type == "xlsx":
        is_data_file = "data" in text_lower or "_data" in url_lower
    elif file_type == "pdf":
        is_results_pdf = "result" in text_lower or "summary" in text_lower
    
    return SurveyLink(
        url=url,
        file_type=file_type,
        survey_type=survey_type,
        link_text=link_text,
        is_data_file=is_data_file,
        is_results_pdf=is_results_pdf,
    )


def get_local_path(url: str, data_dir: Path) -> Path:
    """Generate a local file path for a downloaded file.
    
    Includes the year from the URL path to avoid filename collisions
    (e.g., /2014/April_result.pdf vs /2013/April_result.pdf).
    """
    import re
    
    # Extract filename from URL
    filename = url.split("/")[-1].split("?")[0]
    
    # Extract year from URL path (e.g., /2014/ or /2013/)
    year_match = re.search(r'/(\d{4})/', url)
    if year_match:
        year = year_match.group(1)
        # Check if filename already contains the year
        if year not in filename:
            # Prepend year to filename
            name, ext = filename.rsplit(".", 1) if "." in filename else (filename, "")
            filename = f"{year}-{name}.{ext}" if ext else f"{year}-{name}"
    
    return data_dir / filename


def extract_percent_from_text(text: str) -> Optional[float]:
    """Extract a percentage value from text."""
    # Match patterns like "3.13", "3.13%", "3.125 percent"
    patterns = [
        r"(\d+\.?\d*)\s*%",
        r"(\d+\.?\d*)\s*percent",
        r"(\d+\.?\d*)",
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            try:
                value = float(match.group(1))
                return normalize_percent(value)
            except ValueError:
                continue
    
    return None


# Import pandas here to avoid circular import and for normalize_percent
try:
    import pandas as pd
except ImportError:
    pd = None
    logger.warning("pandas not installed, some functionality may be limited")

