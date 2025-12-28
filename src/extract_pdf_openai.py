"""
Extract longer-run federal funds rate percentiles from PDF files using OpenAI API.

This module uses GPT-4.5 to analyze PDF content and extract percentile data.
"""

import base64
import os
import re
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime

from openai import OpenAI

from .utils import (
    logger,
    CONCEPT_FF_LONGER_RUN,
    PANEL_SPD,
    PANEL_SMP,
    PANEL_COMBINED,
    ExtractedPercentile,
    normalize_percent,
)


# Source identifier for OpenAI extraction
SOURCE_PDF_OPENAI = "pdf_openai"


def get_openai_client() -> Optional[OpenAI]:
    """Get OpenAI client using API key from environment."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        logger.error("OPENAI_API_KEY environment variable not set")
        return None
    return OpenAI(api_key=api_key)


def encode_pdf_to_base64(filepath: Path) -> str:
    """Encode a PDF file to base64 for API upload."""
    with open(filepath, "rb") as f:
        return base64.standard_b64encode(f.read()).decode("utf-8")


def extract_text_from_pdf_with_openai(filepath: Path, client: OpenAI) -> Optional[str]:
    """
    Use OpenAI to extract text content from a PDF.
    
    Note: GPT-4.5 can process PDF content when sent as a file.
    """
    try:
        # Read PDF and send to OpenAI for text extraction
        with open(filepath, "rb") as f:
            pdf_content = f.read()
        
        # Use the file upload API for PDFs
        file = client.files.create(
            file=(filepath.name, pdf_content, "application/pdf"),
            purpose="assistants"
        )
        
        # Create a message asking for text extraction
        response = client.chat.completions.create(
            model="gpt-4.5-preview",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": """Extract all text from this PDF document. Focus especially on any sections about:
- "Longer run" or "long run" federal funds rate
- Target federal funds rate expectations
- Percentile values (25th, 50th/median, 75th)

Return the relevant text content."""
                        },
                        {
                            "type": "file",
                            "file": {"file_id": file.id}
                        }
                    ]
                }
            ],
            max_tokens=4000,
        )
        
        # Clean up the uploaded file
        client.files.delete(file.id)
        
        return response.choices[0].message.content
        
    except Exception as e:
        logger.error(f"OpenAI text extraction failed: {e}")
        return None


def extract_percentiles_with_openai(
    filepath: Path,
    file_url: str,
    survey_date: datetime,
    survey_type: str,
    client: OpenAI,
) -> List[ExtractedPercentile]:
    """
    Extract percentiles from a PDF using OpenAI GPT-4.5.
    """
    logger.info(f"Extracting from PDF with OpenAI: {filepath.name}")
    
    try:
        # Read PDF content
        with open(filepath, "rb") as f:
            pdf_bytes = f.read()
        
        # Encode as base64
        pdf_base64 = base64.standard_b64encode(pdf_bytes).decode("utf-8")
        
        # Create extraction prompt
        prompt = """Analyze this NY Fed survey PDF and extract the "Longer run target federal funds rate" percentile data.

Look for a table or section containing:
- 25th Percentile (or P25, 25th Pctl)
- Median (or 50th Percentile, P50)
- 75th Percentile (or P75, 75th Pctl)

The values should be interest rates in percent (e.g., 2.88, 3.13, 3.50).

Return ONLY a JSON object in this exact format:
{
    "found": true/false,
    "pctl25": <number or null>,
    "pctl50": <number or null>,
    "pctl75": <number or null>,
    "page": <page number where found or null>,
    "notes": "<any relevant notes>"
}

If the "longer run" federal funds question is not present in this survey, set found=false and notes="question_not_present"."""

        # Call OpenAI API
        response = client.chat.completions.create(
            model="gpt-4.5-preview",
            messages=[
                {
                    "role": "system",
                    "content": "You are an expert at extracting structured data from Federal Reserve survey documents. Always respond with valid JSON only."
                },
                {
                    "role": "user", 
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:application/pdf;base64,{pdf_base64}"
                            }
                        }
                    ]
                }
            ],
            max_tokens=500,
            temperature=0,
        )
        
        # Parse response
        content = response.choices[0].message.content.strip()
        
        # Extract JSON from response (handle markdown code blocks)
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
        
        import json
        data = json.loads(content)
        
        # Build result
        panel = {
            PANEL_SPD: PANEL_SPD,
            PANEL_SMP: PANEL_SMP,
        }.get(survey_type, PANEL_COMBINED)
        
        pctl25 = normalize_percent(data.get("pctl25")) if data.get("pctl25") else None
        pctl50 = normalize_percent(data.get("pctl50")) if data.get("pctl50") else None
        pctl75 = normalize_percent(data.get("pctl75")) if data.get("pctl75") else None
        
        notes = data.get("notes") if not data.get("found", True) else None
        pdf_page = data.get("page")
        
        return [ExtractedPercentile(
            survey_date=survey_date,
            panel=panel,
            concept=CONCEPT_FF_LONGER_RUN,
            pctl25=pctl25,
            pctl50=pctl50,
            pctl75=pctl75,
            source=SOURCE_PDF_OPENAI,
            file_url=file_url,
            local_path=str(filepath),
            pdf_page=pdf_page,
            notes=notes,
        )]
        
    except Exception as e:
        logger.error(f"OpenAI extraction failed for {filepath.name}: {e}")
        return [ExtractedPercentile(
            survey_date=survey_date,
            panel=PANEL_COMBINED,
            concept=CONCEPT_FF_LONGER_RUN,
            pctl25=None,
            pctl50=None,
            pctl75=None,
            source=SOURCE_PDF_OPENAI,
            file_url=file_url,
            local_path=str(filepath),
            notes=f"openai_error: {str(e)[:100]}",
        )]


def extract_from_pdf_openai(
    filepath: Path,
    file_url: str,
    survey_date: datetime,
    survey_type: str = "merged",
) -> List[ExtractedPercentile]:
    """
    Extract longer-run federal funds rate percentiles from a PDF using OpenAI.
    
    Args:
        filepath: Path to the PDF file
        file_url: Original URL of the file
        survey_date: Date of the survey
        survey_type: Type of survey (SPD, SMP, or merged)
    
    Returns:
        List of ExtractedPercentile objects
    """
    client = get_openai_client()
    if not client:
        return [ExtractedPercentile(
            survey_date=survey_date,
            panel=PANEL_COMBINED,
            concept=CONCEPT_FF_LONGER_RUN,
            pctl25=None,
            pctl50=None,
            pctl75=None,
            source=SOURCE_PDF_OPENAI,
            file_url=file_url,
            local_path=str(filepath),
            notes="openai_api_key_not_set",
        )]
    
    return extract_percentiles_with_openai(
        filepath=filepath,
        file_url=file_url,
        survey_date=survey_date,
        survey_type=survey_type,
        client=client,
    )

