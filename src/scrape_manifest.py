"""
Scrape the NY Fed Survey of Market Expectations page to build a manifest of survey files.

This module parses the landing page to identify:
- Survey meeting dates
- Associated XLSX data files
- Associated PDF results files
- Survey types (SPD, SMP, or merged)
"""

import re
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from .utils import (
    logger,
    NYFED_BASE_URL,
    SURVEY_PAGE_URL,
    SurveyLink,
    SurveyMeeting,
    PANEL_SPD,
    PANEL_SMP,
    PANEL_MERGED,
    parse_date_from_label,
    classify_survey_link,
)


def fetch_page_content(url: str, timeout: int = 30) -> str:
    """Fetch the HTML content of a page."""
    logger.info(f"Fetching page: {url}")
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    
    response = requests.get(url, headers=headers, timeout=timeout)
    response.raise_for_status()
    
    return response.text


# Month abbreviation to number mapping
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


def extract_links_from_html(html: str) -> List[Dict]:
    """
    Extract all survey file links from the raw HTML using regex.
    
    This is more reliable than BeautifulSoup for this page structure.
    """
    links = []
    
    # Pattern to match href attributes with xlsx or pdf extensions
    href_pattern = re.compile(
        r'href="(/medialibrary/media/markets/survey/[^"]+\.(xlsx|pdf))"',
        re.IGNORECASE
    )
    
    for match in href_pattern.finditer(html):
        path = match.group(1)
        file_type = match.group(2).lower()
        full_url = urljoin(NYFED_BASE_URL, path)
        
        links.append({
            "url": full_url,
            "path": path,
            "file_type": file_type,
        })
    
    logger.info(f"Found {len(links)} file links via regex extraction")
    return links


def parse_date_from_url(url: str) -> Tuple[Optional[datetime], Optional[str]]:
    """
    Parse meeting date and survey type from a URL.
    
    Returns:
        Tuple of (datetime, survey_type)
    
    URL patterns:
    - 2025: /2025/oct-2025-data.xlsx, /2025/oct-2025-sme-results.pdf
    - 2024: /2024/dec-2024-data.xlsx, /2024/dec-2024-spd-results.pdf
    - 2023: /2023/jul-2023-data.xlsx
    - Older: /2014/mp_January_result.pdf, /2013/December_result.pdf
    """
    url_lower = url.lower()
    
    # Extract year from path like /2025/ or /2024/
    year_match = re.search(r'/(\d{4})/', url_lower)
    if not year_match:
        return None, None
    year = int(year_match.group(1))
    
    # Determine survey type from filename
    survey_type = None
    filename = url.split('/')[-1].lower()
    
    if 'sme' in filename:
        survey_type = PANEL_MERGED
    elif 'spd' in filename or 'pd' in filename or 'primary' in filename.lower():
        survey_type = PANEL_SPD
    elif 'smp' in filename or 'mp' in filename or 'participant' in filename.lower():
        survey_type = PANEL_SMP
    elif 'data' in filename and year >= 2023:
        # Data files from 2023+ are combined/merged
        survey_type = PANEL_MERGED
    elif year <= 2014:
        # Pre-2014 files without mp_ prefix are SPD (Primary Dealers only)
        if 'mp_' not in filename and 'mp-' not in filename:
            survey_type = PANEL_SPD
        else:
            survey_type = PANEL_SMP
    
    # Extract month from filename
    # Patterns: oct-2025, dec-2024, apr-may-2024, December, January, etc.
    month = None
    
    # Try pattern like "oct-2025" or "dec-2024"
    month_year_match = re.search(
        r'(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[^a-z]*(\d{4})',
        filename,
        re.IGNORECASE
    )
    if month_year_match:
        month_str = month_year_match.group(1).lower()
        month = MONTH_MAP.get(month_str)
    
    # Try full month names
    if not month:
        for month_name, month_num in MONTH_MAP.items():
            if month_name in filename:
                month = month_num
                break
    
    if month:
        return datetime(year, month, 1), survey_type
    
    return None, survey_type


def classify_file_type(url: str, filename: str) -> Dict[str, bool]:
    """
    Classify a file as data file, results file, or questions file.
    """
    filename_lower = filename.lower()
    
    is_data = 'data' in filename_lower and url.endswith('.xlsx')
    is_results = 'result' in filename_lower and url.endswith('.pdf')
    is_questions = 'survey' in filename_lower and 'result' not in filename_lower and url.endswith('.pdf')
    
    return {
        "is_data_file": is_data,
        "is_results_pdf": is_results,
        "is_questions_pdf": is_questions,
    }


def group_links_by_meeting(raw_links: List[Dict]) -> List[SurveyMeeting]:
    """
    Group raw links by their meeting dates.
    """
    # Parse dates and types for all links
    parsed_links = []
    for raw in raw_links:
        url = raw["url"]
        file_type = raw["file_type"]
        filename = url.split("/")[-1]
        
        meeting_date, survey_type = parse_date_from_url(url)
        
        if not meeting_date:
            logger.debug(f"Could not parse date from: {url}")
            continue
        
        if not survey_type:
            # Default to merged for data files, SPD for older PDFs
            if file_type == "xlsx":
                survey_type = PANEL_MERGED
            else:
                survey_type = PANEL_SPD
        
        file_info = classify_file_type(url, filename)
        
        # Skip question PDFs (we only want results and data)
        if file_info["is_questions_pdf"]:
            continue
        
        parsed_links.append({
            "url": url,
            "file_type": file_type,
            "survey_type": survey_type,
            "meeting_date": meeting_date,
            "filename": filename,
            **file_info,
        })
    
    # Group by date
    meetings_by_date: Dict[str, SurveyMeeting] = {}
    
    for item in parsed_links:
        date_key = item["meeting_date"].strftime("%Y-%m")
        
        if date_key not in meetings_by_date:
            meeting_date = item["meeting_date"]
            label = meeting_date.strftime("%B %Y") + " FOMC"
            
            meetings_by_date[date_key] = SurveyMeeting(
                meeting_date=meeting_date,
                meeting_label=label,
                year=meeting_date.year,
                links=[],
            )
        
        survey_link = SurveyLink(
            url=item["url"],
            file_type=item["file_type"],
            survey_type=item["survey_type"],
            link_text=item["filename"],
            is_data_file=item["is_data_file"],
            is_results_pdf=item["is_results_pdf"],
        )
        
        meetings_by_date[date_key].links.append(survey_link)
    
    # Sort by date (newest first)
    sorted_meetings = sorted(
        meetings_by_date.values(),
        key=lambda m: m.meeting_date,
        reverse=True,
    )
    
    return sorted_meetings


def scrape_manifest(
    start_year: int = 2011,
    end_year: int = 2025,
    page_url: str = SURVEY_PAGE_URL,
) -> List[SurveyMeeting]:
    """
    Scrape the NY Fed survey page and build a manifest of meetings and files.
    
    Args:
        start_year: Earliest year to include
        end_year: Latest year to include
        page_url: URL of the survey landing page
    
    Returns:
        List of SurveyMeeting objects with associated links
    """
    logger.info(f"Scraping manifest for years {start_year}-{end_year}")
    
    try:
        html = fetch_page_content(page_url)
    except requests.RequestException as e:
        logger.error(f"Failed to fetch survey page: {e}")
        raise
    
    # Extract links using regex (more reliable for this page)
    raw_links = extract_links_from_html(html)
    
    # Group by meeting date
    meetings = group_links_by_meeting(raw_links)
    
    # Filter by year range
    filtered_meetings = [
        m for m in meetings
        if start_year <= m.year <= end_year
    ]
    
    logger.info(f"Found {len(filtered_meetings)} meetings in range {start_year}-{end_year}")
    
    # Log summary
    for meeting in filtered_meetings[:10]:  # Show first 10
        xlsx_count = len(meeting.get_xlsx_links())
        pdf_count = len(meeting.get_pdf_links())
        logger.debug(f"  {meeting.meeting_label}: {xlsx_count} XLSX, {pdf_count} PDF")
    
    if len(filtered_meetings) > 10:
        logger.debug(f"  ... and {len(filtered_meetings) - 10} more meetings")
    
    return filtered_meetings


def build_download_manifest(
    meetings: List[SurveyMeeting],
    prefer_xlsx: bool = True,
) -> List[Tuple[SurveyMeeting, SurveyLink]]:
    """
    Build a list of files to download, preferring XLSX over PDF when available.
    
    Args:
        meetings: List of SurveyMeeting objects
        prefer_xlsx: If True, only include PDFs when no XLSX is available
    
    Returns:
        List of (meeting, link) tuples to download
    """
    download_list = []
    
    for meeting in meetings:
        xlsx_links = meeting.get_xlsx_links()
        pdf_links = meeting.get_pdf_links()
        
        if xlsx_links:
            # Add all XLSX links (may have multiple for SPD/SMP split)
            for link in xlsx_links:
                download_list.append((meeting, link))
            
            if not prefer_xlsx:
                # Also add PDFs
                for link in pdf_links:
                    download_list.append((meeting, link))
        elif pdf_links:
            # No XLSX, fall back to PDFs
            for link in pdf_links:
                download_list.append((meeting, link))
        else:
            logger.warning(f"No data files found for {meeting.meeting_label}")
    
    return download_list


if __name__ == "__main__":
    # Test the scraper
    meetings = scrape_manifest(start_year=2020, end_year=2025)
    
    for meeting in meetings:
        print(f"\n{meeting.meeting_label} ({meeting.meeting_date}):")
        for link in meeting.links:
            file_flag = "DATA" if link.is_data_file else ("RESULT" if link.is_results_pdf else "OTHER")
            print(f"  - [{link.survey_type}] [{file_flag}] {link.file_type}: {link.url.split('/')[-1]}")
