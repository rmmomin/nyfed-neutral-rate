"""
Unit tests for the NY Fed survey extractor.

Tests cover:
- Link classification (SPD vs SMP vs merged)
- PDF row parsing regex
- XLSX parsing fallback logic
- Utility functions
"""

import pytest
from datetime import datetime
from pathlib import Path
from io import BytesIO

import pandas as pd

from src.utils import (
    classify_survey_link,
    matches_longer_run_ff,
    normalize_percent,
    parse_date_from_label,
    extract_percent_from_text,
    PANEL_SPD,
    PANEL_SMP,
    PANEL_MERGED,
)
from src.extract_xlsx import (
    find_column_by_patterns,
    detect_percentile_columns,
    extract_percentiles_from_row,
    find_longer_run_rows,
    VALUE_TAG_PATTERNS,
)
from src.extract_pdf import (
    parse_percentiles_from_text,
    parse_percentiles_from_table,
    PERCENTILE_ROW_PATTERNS,
)


class TestLinkClassification:
    """Tests for classifying survey links as SPD, SMP, or merged."""
    
    def test_spd_link_by_url(self):
        """SPD links should be classified correctly based on URL pattern."""
        url = "https://example.com/medialibrary/spd_jan2024_data.xlsx"
        result = classify_survey_link(url, "Data")
        
        assert result is not None
        assert result.survey_type == PANEL_SPD
        assert result.file_type == "xlsx"
        assert result.is_data_file is True
    
    def test_smp_link_by_url(self):
        """SMP links should be classified correctly based on URL pattern."""
        url = "https://example.com/medialibrary/smp_jan2024_data.xlsx"
        result = classify_survey_link(url, "Data")
        
        assert result is not None
        assert result.survey_type == PANEL_SMP
        assert result.file_type == "xlsx"
    
    def test_merged_link_by_url(self):
        """Merged/SME links should be classified correctly."""
        url = "https://example.com/medialibrary/sme_jan2025_data.xlsx"
        result = classify_survey_link(url, "Data")
        
        assert result is not None
        assert result.survey_type == PANEL_MERGED
        assert result.file_type == "xlsx"
    
    def test_spd_link_by_text(self):
        """SPD links should be classified by link text."""
        url = "https://example.com/data.xlsx"
        result = classify_survey_link(url, "Primary Dealers Data")
        
        assert result is not None
        assert result.survey_type == PANEL_SPD
    
    def test_smp_link_by_text(self):
        """SMP links should be classified by link text."""
        url = "https://example.com/data.xlsx"
        result = classify_survey_link(url, "Market Participants Data")
        
        assert result is not None
        assert result.survey_type == PANEL_SMP
    
    def test_pdf_results_classification(self):
        """PDF results files should be classified correctly."""
        url = "https://example.com/spd_results.pdf"
        result = classify_survey_link(url, "SPD Results")
        
        assert result is not None
        assert result.file_type == "pdf"
        assert result.survey_type == PANEL_SPD
        assert result.is_results_pdf is True
    
    def test_non_file_link_returns_none(self):
        """Non-file links should return None."""
        url = "https://example.com/page.html"
        result = classify_survey_link(url, "Press Release")
        
        assert result is None
    
    def test_unclassifiable_file_returns_none(self):
        """Files that can't be classified should return None."""
        url = "https://example.com/random_document.pdf"
        result = classify_survey_link(url, "Other Document")
        
        assert result is None


class TestLongerRunKeywordMatching:
    """Tests for matching longer-run federal funds rate keywords."""
    
    def test_exact_match(self):
        """Exact keyword match should work."""
        text = "Longer run target federal funds rate"
        assert matches_longer_run_ff(text) is True
    
    def test_case_insensitive(self):
        """Matching should be case insensitive."""
        text = "LONGER RUN TARGET FEDERAL FUNDS RATE"
        assert matches_longer_run_ff(text) is True
    
    def test_hyphenated(self):
        """Hyphenated 'longer-run' should match."""
        text = "longer-run federal funds rate target"
        assert matches_longer_run_ff(text) is True
    
    def test_with_other_text(self):
        """Keywords embedded in other text should match."""
        text = "Question 3b: What is your expectation for the longer run target federal funds rate?"
        assert matches_longer_run_ff(text) is True
    
    def test_missing_longer_run(self):
        """Missing 'longer run' should not match."""
        text = "Target federal funds rate for 2025"
        assert matches_longer_run_ff(text) is False
    
    def test_missing_federal_funds(self):
        """Missing 'federal funds' should not match."""
        text = "Longer run inflation expectations"
        assert matches_longer_run_ff(text) is False
    
    def test_abbreviated_keywords(self):
        """Abbreviated keywords like 'fftr' should match."""
        text = "Longer run fftr modal expectation"
        assert matches_longer_run_ff(text) is True


class TestPercentNormalization:
    """Tests for normalizing values to percent format."""
    
    def test_already_percent(self):
        """Values already in percent should not be changed."""
        assert normalize_percent(3.13) == 3.13
        assert normalize_percent(5.0) == 5.0
    
    def test_decimal_form(self):
        """Decimal form should be converted to percent."""
        result = normalize_percent(0.0313)
        assert result == pytest.approx(3.13, rel=0.01)
    
    def test_string_with_percent_sign(self):
        """String with % sign should be parsed."""
        result = normalize_percent("3.13%")
        assert result == pytest.approx(3.13, rel=0.01)
    
    def test_none_value(self):
        """None should return None."""
        assert normalize_percent(None) is None
    
    def test_na_string(self):
        """NA strings should return None."""
        assert normalize_percent("NA") is None
        assert normalize_percent("N/A") is None
        assert normalize_percent("-") is None
    
    def test_edge_case_zero(self):
        """Zero should remain zero (as percent)."""
        # 0.0 is ambiguous but we treat it as 0%
        result = normalize_percent(0.0)
        assert result == 0.0


class TestDateParsing:
    """Tests for parsing dates from labels."""
    
    def test_full_month_name(self):
        """Full month names should parse correctly."""
        result = parse_date_from_label("January 2025 FOMC")
        assert result == datetime(2025, 1, 1)
    
    def test_abbreviated_month(self):
        """Abbreviated month names should parse correctly."""
        result = parse_date_from_label("Jul 2024")
        assert result == datetime(2024, 7, 1)
    
    def test_combined_months(self):
        """Combined month labels (Jul/Aug) should parse to first month."""
        result = parse_date_from_label("Jul/Aug 2024")
        assert result == datetime(2024, 7, 1)
    
    def test_invalid_label(self):
        """Invalid labels should return None."""
        result = parse_date_from_label("Random text")
        assert result is None


class TestPDFPercentileRegex:
    """Tests for PDF percentile row parsing regex."""
    
    def test_25th_percentile_pattern(self):
        """25th percentile patterns should match."""
        text = "25th Pctl 3.13"
        result = parse_percentiles_from_text(text)
        assert result["pctl25"] == pytest.approx(3.13, rel=0.01)
    
    def test_median_pattern(self):
        """Median pattern should match."""
        text = "Median: 3.25%"
        result = parse_percentiles_from_text(text)
        assert result["pctl50"] == pytest.approx(3.25, rel=0.01)
    
    def test_75th_percentile_pattern(self):
        """75th percentile pattern should match."""
        text = "75th Pctl = 3.50"
        result = parse_percentiles_from_text(text)
        assert result["pctl75"] == pytest.approx(3.5, rel=0.01)
    
    def test_all_percentiles_in_block(self):
        """All percentiles in a text block should be extracted."""
        text = """
        25th Pctl: 3.00
        Median: 3.13
        75th Pctl: 3.25
        """
        result = parse_percentiles_from_text(text)
        assert result["pctl25"] == pytest.approx(3.0, rel=0.01)
        assert result["pctl50"] == pytest.approx(3.13, rel=0.01)
        assert result["pctl75"] == pytest.approx(3.25, rel=0.01)
    
    def test_no_match_returns_none(self):
        """Non-matching text should return None values."""
        text = "Some random text without percentiles"
        result = parse_percentiles_from_text(text)
        assert result["pctl25"] is None
        assert result["pctl50"] is None
        assert result["pctl75"] is None


class TestPDFTableParsing:
    """Tests for PDF table parsing."""
    
    def test_vertical_table_format(self):
        """Vertical table format should parse correctly."""
        table = [
            ["Statistic", "Value"],
            ["25th Pctl", "3.00"],
            ["Median", "3.13"],
            ["75th Pctl", "3.25"],
        ]
        result = parse_percentiles_from_table(table)
        assert result["pctl25"] == pytest.approx(3.0, rel=0.01)
        assert result["pctl50"] == pytest.approx(3.13, rel=0.01)
        assert result["pctl75"] == pytest.approx(3.25, rel=0.01)
    
    def test_horizontal_table_format(self):
        """Horizontal table format should parse correctly."""
        table = [
            ["25th Pctl", "Median", "75th Pctl"],
            ["3.00", "3.13", "3.25"],
        ]
        result = parse_percentiles_from_table(table)
        assert result["pctl25"] == pytest.approx(3.0, rel=0.01)
        assert result["pctl50"] == pytest.approx(3.13, rel=0.01)
        assert result["pctl75"] == pytest.approx(3.25, rel=0.01)
    
    def test_empty_table(self):
        """Empty table should return None values."""
        result = parse_percentiles_from_table([])
        assert all(v is None for v in result.values())


class TestXLSXParsing:
    """Tests for XLSX parsing logic."""
    
    def test_find_column_by_patterns(self):
        """Column pattern matching should work."""
        columns = ["question_text", "value_tag", "p25", "median", "p75"]
        
        result = find_column_by_patterns(columns, VALUE_TAG_PATTERNS)
        assert result == "value_tag"
    
    def test_detect_percentile_columns(self):
        """Percentile column detection should work."""
        columns = ["concept", "p25", "median", "p75", "n_responses"]
        
        result = detect_percentile_columns(columns)
        assert result["pctl25"] == "p25"
        assert result["pctl50"] == "median"
        assert result["pctl75"] == "p75"
    
    def test_detect_percentile_columns_with_panel_suffix(self):
        """Panel-specific percentile columns should be detected."""
        columns = ["concept", "p25_dealer", "median_dealer", "p75_dealer", 
                   "p25_participant", "median_participant", "p75_participant"]
        
        dealer_cols = detect_percentile_columns(columns, "dealer")
        assert dealer_cols["pctl25"] == "p25_dealer"
        assert dealer_cols["pctl50"] == "median_dealer"
        assert dealer_cols["pctl75"] == "p75_dealer"
    
    def test_extract_percentiles_from_row(self):
        """Extracting percentiles from a DataFrame row should work."""
        row = pd.Series({
            "concept": "fftr_longrun",
            "p25": 3.0,
            "median": 3.13,
            "p75": 3.25,
        })
        columns = {"pctl25": "p25", "pctl50": "median", "pctl75": "p75"}
        
        result = extract_percentiles_from_row(row, columns)
        assert result["pctl25"] == pytest.approx(3.0, rel=0.01)
        assert result["pctl50"] == pytest.approx(3.13, rel=0.01)
        assert result["pctl75"] == pytest.approx(3.25, rel=0.01)
    
    def test_find_longer_run_rows_by_value_tag(self):
        """Finding longer-run rows by value_tag should work."""
        df = pd.DataFrame({
            "value_tag": ["fftr_modalpe_2025", "fftr_modalpe_longerrun", "inflation_5yr"],
            "p25": [3.5, 3.0, 2.0],
            "median": [3.75, 3.13, 2.5],
            "p75": [4.0, 3.25, 3.0],
        })
        
        result = find_longer_run_rows(df, value_tag_col="value_tag")
        assert len(result) == 1
        assert result.iloc[0]["value_tag"] == "fftr_modalpe_longerrun"
    
    def test_find_longer_run_rows_by_question_text(self):
        """Finding longer-run rows by question text should work."""
        df = pd.DataFrame({
            "question_text": [
                "Target federal funds rate for Q1 2025",
                "Longer run target federal funds rate",
                "Core PCE inflation",
            ],
            "p25": [3.5, 3.0, 2.0],
            "median": [3.75, 3.13, 2.5],
            "p75": [4.0, 3.25, 3.0],
        })
        
        result = find_longer_run_rows(df, question_text_col="question_text")
        assert len(result) == 1
        assert "longer run" in result.iloc[0]["question_text"].lower()


class TestExtractPercentFromText:
    """Tests for extracting percent values from text strings."""
    
    def test_plain_number(self):
        """Plain numbers should be extracted."""
        result = extract_percent_from_text("The value is 3.13")
        assert result == pytest.approx(3.13, rel=0.01)
    
    def test_number_with_percent_sign(self):
        """Numbers with % sign should be extracted."""
        result = extract_percent_from_text("3.13%")
        assert result == pytest.approx(3.13, rel=0.01)
    
    def test_number_with_percent_word(self):
        """Numbers with 'percent' word should be extracted."""
        result = extract_percent_from_text("3.13 percent")
        assert result == pytest.approx(3.13, rel=0.01)
    
    def test_no_number(self):
        """Text without numbers should return None."""
        result = extract_percent_from_text("No numbers here")
        assert result is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

