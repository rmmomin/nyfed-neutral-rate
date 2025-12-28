"""
Extract longer-run federal funds rate percentiles from PDF files.

This module handles:
- Text extraction using pdfplumber
- OCR fallback using pytesseract when text extraction fails
- Parsing percentile tables from the extracted text
- Finding the correct section regardless of question numbering
"""

import re
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from datetime import datetime
import tempfile

import pdfplumber

from .utils import (
    logger,
    CONCEPT_FF_LONGER_RUN,
    PANEL_SPD,
    PANEL_SMP,
    PANEL_COMBINED,
    SOURCE_PDF_TEXT,
    SOURCE_PDF_OCR,
    ExtractedPercentile,
    matches_longer_run_ff,
    normalize_percent,
    LONGER_RUN_KEYWORDS,
    FEDERAL_FUNDS_KEYWORDS,
    PERCENTILE_PATTERNS,
)


# Try to import OCR dependencies (optional)
try:
    from pdf2image import convert_from_path
    import pytesseract
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False
    logger.warning("OCR dependencies not available (pdf2image, pytesseract)")


# Regex patterns for extracting percentile values
PERCENTILE_ROW_PATTERNS = [
    # Pattern: "25th Pctl 3.13" or "25th Pctl: 3.13" or "25th Pctl 3.13%"
    (r"25th\s*p(?:e?r)?c?t?l?\.?\s*[:=]?\s*(\d+\.?\d*)\s*%?", "pctl25"),
    (r"median\s*[:=]?\s*(\d+\.?\d*)\s*%?", "pctl50"),
    (r"75th\s*p(?:e?r)?c?t?l?\.?\s*[:=]?\s*(\d+\.?\d*)\s*%?", "pctl75"),
    # Alternative patterns
    (r"p25\s*[:=]?\s*(\d+\.?\d*)\s*%?", "pctl25"),
    (r"p50\s*[:=]?\s*(\d+\.?\d*)\s*%?", "pctl50"),
    (r"p75\s*[:=]?\s*(\d+\.?\d*)\s*%?", "pctl75"),
]

# Table header patterns
TABLE_PATTERNS = [
    # Header row pattern: look for percentile column headers
    r"(?:statistic|measure).*?25th.*?median.*?75th",
    r"25th\s+(?:pctl|percentile).*?50th\s+(?:pctl|percentile|median).*?75th\s+(?:pctl|percentile)",
]


def extract_text_with_pdfplumber(filepath: Path) -> List[Tuple[int, str]]:
    """
    Extract text from PDF using pdfplumber.
    
    Returns:
        List of (page_number, page_text) tuples (1-indexed page numbers)
    """
    pages = []
    
    try:
        with pdfplumber.open(filepath) as pdf:
            for i, page in enumerate(pdf.pages, start=1):
                text = page.extract_text() or ""
                pages.append((i, text))
                logger.debug(f"Page {i}: {len(text)} chars extracted")
    except Exception as e:
        logger.error(f"Failed to extract text from {filepath}: {e}")
    
    return pages


def extract_tables_with_pdfplumber(filepath: Path) -> List[Tuple[int, List[List[str]]]]:
    """
    Extract tables from PDF using pdfplumber.
    
    Returns:
        List of (page_number, table_data) tuples
    """
    tables = []
    
    try:
        with pdfplumber.open(filepath) as pdf:
            for i, page in enumerate(pdf.pages, start=1):
                page_tables = page.extract_tables()
                for table in page_tables:
                    if table:
                        tables.append((i, table))
    except Exception as e:
        logger.error(f"Failed to extract tables from {filepath}: {e}")
    
    return tables


def ocr_page(filepath: Path, page_num: int, dpi: int = 200) -> str:
    """
    OCR a specific page of a PDF.
    
    Args:
        filepath: Path to PDF file
        page_num: Page number (1-indexed)
        dpi: Resolution for rendering
    
    Returns:
        OCR text for the page
    """
    if not OCR_AVAILABLE:
        logger.warning("OCR not available")
        return ""
    
    try:
        # Convert specific page to image
        images = convert_from_path(
            filepath,
            first_page=page_num,
            last_page=page_num,
            dpi=dpi,
        )
        
        if not images:
            return ""
        
        # OCR the image
        text = pytesseract.image_to_string(images[0])
        logger.debug(f"OCR page {page_num}: {len(text)} chars")
        
        return text
        
    except Exception as e:
        logger.error(f"OCR failed for page {page_num}: {e}")
        return ""


def find_longer_run_section(
    pages: List[Tuple[int, str]],
) -> List[Tuple[int, str, int, int]]:
    """
    Find pages/sections containing the longer-run federal funds rate question.
    
    Returns:
        List of (page_num, text_section, start_pos, end_pos) tuples
    """
    sections = []
    
    for page_num, text in pages:
        if not text:
            continue
        
        text_lower = text.lower()
        
        # Check if page contains longer-run FF keywords
        if matches_longer_run_ff(text):
            # Find the approximate position of the match
            for lr_pattern in LONGER_RUN_KEYWORDS:
                for ff_pattern in FEDERAL_FUNDS_KEYWORDS:
                    combined = f"({lr_pattern}).*?({ff_pattern})"
                    match = re.search(combined, text_lower, re.DOTALL | re.IGNORECASE)
                    if match:
                        # Extract a section around the match (500 chars before/after)
                        start = max(0, match.start() - 500)
                        end = min(len(text), match.end() + 1500)
                        section = text[start:end]
                        sections.append((page_num, section, start, end))
                        break
                if sections and sections[-1][0] == page_num:
                    break
    
    return sections


def parse_percentiles_from_text(text: str) -> Dict[str, Optional[float]]:
    """
    Parse percentile values from a text section.
    
    Returns:
        Dict with pctl25, pctl50, pctl75 values
    """
    result = {"pctl25": None, "pctl50": None, "pctl75": None}
    
    for pattern, pctl_key in PERCENTILE_ROW_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            try:
                value = float(match.group(1))
                result[pctl_key] = normalize_percent(value)
            except ValueError:
                continue
    
    return result


def parse_percentiles_from_table(
    table: List[List[str]],
) -> Dict[str, Optional[float]]:
    """
    Parse percentile values from a table structure.
    
    Expected table format:
    Statistic | Value
    25th Pctl | 3.13
    Median    | 3.25
    75th Pctl | 3.50
    
    Or horizontal:
    25th Pctl | Median | 75th Pctl
    3.13      | 3.25   | 3.50
    """
    result = {"pctl25": None, "pctl50": None, "pctl75": None}
    
    if not table or len(table) < 2:
        return result
    
    # Try to find column headers
    header_row = None
    for i, row in enumerate(table):
        row_text = " ".join(str(cell or "") for cell in row).lower()
        if any(kw in row_text for kw in ["25th", "median", "75th", "percentile"]):
            header_row = i
            break
    
    if header_row is not None:
        # Check if this is a header row (percentiles in columns)
        headers = table[header_row]
        header_text = " ".join(str(h or "").lower() for h in headers)
        
        if "25th" in header_text and "median" in header_text:
            # Horizontal format - values in next row
            if header_row + 1 < len(table):
                values_row = table[header_row + 1]
                
                for j, header in enumerate(headers):
                    if j < len(values_row):
                        header_lower = str(header or "").lower()
                        value = values_row[j]
                        
                        try:
                            num = float(str(value).replace("%", "").strip())
                        except (ValueError, TypeError):
                            continue
                        
                        if "25th" in header_lower:
                            result["pctl25"] = normalize_percent(num)
                        elif "median" in header_lower or "50th" in header_lower:
                            result["pctl50"] = normalize_percent(num)
                        elif "75th" in header_lower:
                            result["pctl75"] = normalize_percent(num)
    
    # Try vertical format
    if all(v is None for v in result.values()):
        for row in table:
            if len(row) >= 2:
                label = str(row[0] or "").lower()
                value = row[-1]  # Take last column as value
                
                try:
                    num = float(str(value).replace("%", "").strip())
                except (ValueError, TypeError):
                    continue
                
                if "25th" in label or "p25" in label:
                    result["pctl25"] = normalize_percent(num)
                elif "median" in label or "50th" in label or "p50" in label:
                    result["pctl50"] = normalize_percent(num)
                elif "75th" in label or "p75" in label:
                    result["pctl75"] = normalize_percent(num)
    
    return result


def extract_from_pdf(
    filepath: Path,
    file_url: str,
    survey_date: datetime,
    survey_type: str = "merged",
    use_ocr: bool = True,
) -> List[ExtractedPercentile]:
    """
    Extract longer-run federal funds rate percentiles from a PDF file.
    
    Args:
        filepath: Path to the PDF file
        file_url: Original URL of the file
        survey_date: Date of the survey
        survey_type: Type of survey (SPD, SMP, or merged)
        use_ocr: Whether to use OCR if text extraction fails
    
    Returns:
        List of ExtractedPercentile objects
    """
    logger.info(f"Extracting from PDF: {filepath.name}")
    
    results = []
    source = SOURCE_PDF_TEXT
    pdf_page = None
    
    # Step 1: Try text extraction with pdfplumber
    pages = extract_text_with_pdfplumber(filepath)
    total_text = sum(len(text) for _, text in pages)
    logger.debug(f"Extracted {total_text} total chars from {len(pages)} pages")
    
    # Step 2: Find sections containing longer-run FF
    sections = find_longer_run_section(pages)
    logger.debug(f"Found {len(sections)} candidate sections")
    
    # Step 3: Try to extract percentiles from text sections
    pctls = {"pctl25": None, "pctl50": None, "pctl75": None}
    
    for page_num, section_text, _, _ in sections:
        parsed = parse_percentiles_from_text(section_text)
        
        # Update with any found values
        for key, value in parsed.items():
            if value is not None and pctls[key] is None:
                pctls[key] = value
                pdf_page = page_num
        
        if all(v is not None for v in pctls.values()):
            break
    
    # Step 4: Try table extraction if text parsing incomplete
    if not all(v is not None for v in pctls.values()):
        tables = extract_tables_with_pdfplumber(filepath)
        
        for page_num, table in tables:
            # Check if table is in a relevant section
            table_text = " ".join(
                str(cell or "") for row in table for cell in row
            )
            
            if matches_longer_run_ff(table_text):
                parsed = parse_percentiles_from_table(table)
                
                for key, value in parsed.items():
                    if value is not None and pctls[key] is None:
                        pctls[key] = value
                        pdf_page = page_num
                
                if all(v is not None for v in pctls.values()):
                    break
    
    # Step 5: OCR fallback if enabled and text extraction failed
    if use_ocr and OCR_AVAILABLE and not all(v is not None for v in pctls.values()):
        logger.info(f"Attempting OCR for {filepath.name}")
        source = SOURCE_PDF_OCR
        
        # First, try OCR on pages where we found partial matches
        ocr_pages = set()
        for page_num, _, _, _ in sections:
            ocr_pages.add(page_num)
        
        # If no sections found, OCR first 5 pages
        if not ocr_pages:
            ocr_pages = set(range(1, min(6, len(pages) + 1)))
        
        for page_num in sorted(ocr_pages):
            ocr_text = ocr_page(filepath, page_num)
            
            if matches_longer_run_ff(ocr_text):
                parsed = parse_percentiles_from_text(ocr_text)
                
                for key, value in parsed.items():
                    if value is not None and pctls[key] is None:
                        pctls[key] = value
                        pdf_page = page_num
                
                if all(v is not None for v in pctls.values()):
                    break
        
        # Expand OCR search if still incomplete
        if not all(v is not None for v in pctls.values()):
            remaining_pages = [
                p for p, _ in pages
                if p not in ocr_pages
            ]
            
            for page_num in remaining_pages[:10]:  # Limit expansion
                ocr_text = ocr_page(filepath, page_num)
                
                if matches_longer_run_ff(ocr_text):
                    parsed = parse_percentiles_from_text(ocr_text)
                    
                    for key, value in parsed.items():
                        if value is not None and pctls[key] is None:
                            pctls[key] = value
                            pdf_page = page_num
                    
                    if all(v is not None for v in pctls.values()):
                        break
    
    # Step 6: Build result
    panel = {
        PANEL_SPD: PANEL_SPD,
        PANEL_SMP: PANEL_SMP,
        "merged": PANEL_COMBINED,
    }.get(survey_type, PANEL_COMBINED)
    
    notes = None
    if not any(v is not None for v in pctls.values()):
        notes = "question_not_present"
        if not sections:
            notes += "; no_matching_sections_found"
    
    results.append(ExtractedPercentile(
        survey_date=survey_date,
        panel=panel,
        concept=CONCEPT_FF_LONGER_RUN,
        pctl25=pctls["pctl25"],
        pctl50=pctls["pctl50"],
        pctl75=pctls["pctl75"],
        source=source,
        file_url=file_url,
        local_path=str(filepath),
        pdf_page=pdf_page,
        notes=notes,
    ))
    
    logger.info(
        f"Extracted from {filepath.name}: "
        f"25th={pctls['pctl25']}, median={pctls['pctl50']}, 75th={pctls['pctl75']}"
    )
    
    return results


if __name__ == "__main__":
    # Test with a sample file
    import sys
    
    if len(sys.argv) > 1:
        test_file = Path(sys.argv[1])
        if test_file.exists():
            results = extract_from_pdf(
                test_file,
                file_url="test://example.pdf",
                survey_date=datetime(2024, 12, 1),
            )
            
            for r in results:
                print(f"\nPanel: {r.panel}")
                print(f"  Source: {r.source}")
                print(f"  Page: {r.pdf_page}")
                print(f"  25th: {r.pctl25}")
                print(f"  Median: {r.pctl50}")
                print(f"  75th: {r.pctl75}")
                if r.notes:
                    print(f"  Notes: {r.notes}")

