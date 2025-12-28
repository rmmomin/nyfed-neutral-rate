# NY Fed Longer-Run Federal Funds Rate Extractor

A Python tool that extracts "Longer run target federal funds rate" percentiles (25th, median, 75th) from the New York Federal Reserve's Survey of Market Expectations.

## Overview

This project scrapes the [NY Fed Survey of Market Expectations](https://www.newyorkfed.org/markets/market-intelligence/survey-of-market-expectations) page, downloads survey data files, and extracts the longer-run target federal funds rate percentile values into a tidy CSV format.

### Data Sources

The NY Fed publishes survey results in multiple formats across different time periods:

- **2025+**: Merged "Survey of Market Expectations" (SME) with optional dealer/participant split
- **2014-2024**: Two separate surveys:
  - SPD (Survey of Primary Dealers)
  - SMP (Survey of Market Participants)
- **Earlier years**: May be PDF-only

### Extraction Strategy

1. **XLSX preferred**: When a "Data" XLSX file exists, extract from it (more reliable)
2. **PDF fallback**: Parse Results PDFs using text extraction (pdfplumber)
3. **OCR fallback**: When PDF text extraction fails, use OCR (pytesseract)

## Installation

### Prerequisites

- Python 3.9+
- For OCR support: Tesseract OCR and Poppler

#### macOS

```bash
# Install Tesseract and Poppler for OCR support
brew install tesseract poppler
```

#### Ubuntu/Debian

```bash
sudo apt-get install tesseract-ocr poppler-utils
```

### Python Dependencies

```bash
# Clone or navigate to the project
cd neutral-rate-survey

# Create a virtual environment (recommended)
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

## Usage

### Basic Usage

```bash
# Run the full pipeline for years 2011-2025
python -m src.pipeline

# Or with specific year range
python -m src.pipeline --start-year 2020 --end-year 2025
```

### CLI Options

```bash
python -m src.pipeline --help
```

| Option | Default | Description |
|--------|---------|-------------|
| `--start-year` | 2011 | Earliest year to include |
| `--end-year` | 2025 | Latest year to include |
| `--data-dir` | `data_raw/` | Directory for downloaded files |
| `--output-dir` | `data_out/` | Directory for output CSV |
| `--output-file` | `nyfed_ff_longrun_percentiles.csv` | Output filename |
| `--redownload` | False | Force re-download of existing files |
| `--use-ocr` / `--no-ocr` | True | Enable/disable OCR for PDFs |
| `--max-files` | None | Limit downloads (for testing) |
| `--skip-download` | False | Skip download, use existing files |
| `-v, --verbose` | False | Enable debug logging |

### Examples

```bash
# Download and extract only 2024 data
python -m src.pipeline --start-year 2024 --end-year 2024

# Re-download all files (ignore cache)
python -m src.pipeline --redownload

# Process without OCR (faster, may miss some PDFs)
python -m src.pipeline --no-ocr

# Test with just 5 files
python -m src.pipeline --max-files 5 --verbose

# Use existing downloads, just re-extract
python -m src.pipeline --skip-download
```

## Output Format

The output CSV (`data_out/nyfed_ff_longrun_percentiles.csv`) has the following columns:

| Column | Type | Description |
|--------|------|-------------|
| `survey_date` | YYYY-MM-DD | Date of the survey (first of month) |
| `panel` | string | SPD, SMP, Dealer, Participant, or Combined |
| `concept` | string | Always `ff_longer_run_target` |
| `pctl25` | float | 25th percentile (%, e.g., 3.00) |
| `pctl50` | float | Median/50th percentile (%) |
| `pctl75` | float | 75th percentile (%) |
| `source` | string | `xlsx`, `pdf_text`, or `pdf_ocr` |
| `file_url` | string | Original URL of the source file |
| `local_path` | string | Path to downloaded file |
| `pdf_page` | int | Page number (PDF sources only) |
| `notes` | string | Notes, e.g., `question_not_present` |

### Sample Output

```csv
survey_date,panel,concept,pctl25,pctl50,pctl75,source,file_url,local_path,pdf_page,notes
2025-01-01,Combined,ff_longer_run_target,3.0,3.13,3.25,xlsx,https://...,data_raw/sme_jan2025.xlsx,,
2024-12-01,Dealer,ff_longer_run_target,3.0,3.13,3.25,xlsx,https://...,data_raw/spd_dec2024.xlsx,,
2024-12-01,Participant,ff_longer_run_target,3.0,3.06,3.13,xlsx,https://...,data_raw/smp_dec2024.xlsx,,
```

## Project Structure

```
neutral-rate-survey/
├── src/
│   ├── __init__.py
│   ├── utils.py           # Constants, data classes, utilities
│   ├── scrape_manifest.py # Scrape survey page for file links
│   ├── download.py        # Download XLSX/PDF files
│   ├── extract_xlsx.py    # Parse XLSX files
│   ├── extract_pdf.py     # Parse PDFs (text + OCR)
│   └── pipeline.py        # CLI entrypoint
├── tests/
│   ├── __init__.py
│   └── test_parsing.py    # Unit tests
├── data_raw/              # Downloaded files (git-ignored)
├── data_out/              # Output CSV (git-ignored)
├── requirements.txt
└── README.md
```

## Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src --cov-report=term-missing

# Run specific test file
pytest tests/test_parsing.py -v
```

## Technical Details

### XLSX Parsing

The XLSX parser handles multiple data formats:

1. **By value_tag**: Looks for `fftr_modalpe_longerrun` in a `value_tag` column
2. **By question text**: Matches text containing "longer run" + "federal funds"
3. **Panel detection**: Automatically detects SPD/SMP/Dealer/Participant columns
4. **Format normalization**: Converts decimal form (0.0313) to percent (3.13)

### PDF Parsing

1. **Text extraction**: Uses pdfplumber to extract embedded text
2. **Section finding**: Locates sections with "longer run" + "federal funds" keywords
3. **Value extraction**: Regex patterns for "25th Pctl", "Median", "75th Pctl"
4. **Table parsing**: Handles both vertical and horizontal table formats
5. **OCR fallback**: Renders pages as images and runs pytesseract

### Keyword Matching

The tool uses flexible keyword matching that works regardless of question numbering:

- "Longer run" variations: `longer run`, `longer-run`, `longrun`
- "Federal funds" variations: `federal funds`, `fed funds`, `fftr`, `target rate`

## Limitations

1. **Historical coverage**: Early surveys (pre-2014) may have different formats not fully supported
2. **OCR accuracy**: OCR may produce errors with low-quality scans or unusual fonts
3. **Rate changes**: If the NY Fed significantly changes their file format or naming conventions, the scraper may need updates
4. **Network dependency**: Requires internet access to scrape and download

## Troubleshooting

### "No meetings found"

- Check your internet connection
- The NY Fed page structure may have changed; inspect the page manually

### "Failed to extract text from PDF"

- Ensure poppler is installed for PDF rendering
- Try with `--verbose` to see detailed error messages

### "OCR dependencies not available"

```bash
# macOS
brew install tesseract poppler

# Ubuntu/Debian  
sudo apt-get install tesseract-ocr poppler-utils

# Then reinstall Python packages
pip install pdf2image pytesseract
```

### Missing percentiles (all None)

- The longer-run question may not be present in that survey
- Check the `notes` column for details
- Manually inspect the source file

## License

MIT License - see LICENSE file for details.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Submit a pull request

## Acknowledgments

Data source: [Federal Reserve Bank of New York](https://www.newyorkfed.org/)

