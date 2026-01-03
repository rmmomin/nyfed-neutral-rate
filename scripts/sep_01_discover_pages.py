#!/usr/bin/env python3
"""
Discover all FOMC SEP projection materials URLs from the Federal Reserve website.

Scrapes:
- Historical year pages (2012-2019) for PDF URLs
- FOMC calendar (2020+) for HTML page URLs

Outputs:
  - data_out/sep_page_urls.txt (HTML pages, 2020+)
  - data_out/sep_pdf_urls.txt (PDFs, 2012-2019)
"""

import re
import time
from pathlib import Path
from typing import List, Tuple
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


BASE = "https://www.federalreserve.gov"
CAL_URL = urljoin(BASE, "/monetarypolicy/fomccalendars.htm")
HIST_INDEX_URL = urljoin(BASE, "/monetarypolicy/fomc_historical_year.htm")

# Match SEP projection table pages (HTML, 2020+)
PROJ_PAGE_RE = re.compile(r"/monetarypolicy/fomcprojtabl(\d{8})\.htm$", re.I)

# Match SEP PDF compilation files (2012-2019)
# Pattern: /monetarypolicy/files/FOMC20140319SEPcompilation.pdf
SEP_PDF_RE = re.compile(r"/monetarypolicy/files/FOMC(\d{8})SEPcompilation\.pdf$", re.I)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; sep-dotplot-scraper/1.0)",
}


def fetch_soup(url: str, timeout: int = 60) -> BeautifulSoup:
    """Fetch URL and return BeautifulSoup object."""
    r = requests.get(url, headers=HEADERS, timeout=timeout)
    r.raise_for_status()
    return BeautifulSoup(r.text, "html.parser")


def discover_sep_urls() -> Tuple[List[str], List[str]]:
    """
    Discover all SEP projection-material URLs.

    Returns:
        html_pages: URLs for HTML pages (2020+)
        pdf_urls: URLs for PDF files (2012-2019)
    """
    html_pages = set()
    pdf_urls = set()

    # 1) Historical year pages (2012-2019) - look for PDFs
    print("Fetching historical year index...")
    hist_index = fetch_soup(HIST_INDEX_URL)

    year_pages = []
    for a in hist_index.select("a[href]"):
        href = urljoin(BASE, a["href"])
        if "monetarypolicy/fomchistorical20" in href.lower() and href.lower().endswith(".htm"):
            year_pages.append(href)

    year_pages = sorted(set(year_pages))
    print(f"  Found {len(year_pages)} historical year pages")

    for yp in year_pages:
        print(f"  Scanning {yp}...")
        soup = fetch_soup(yp)
        for a in soup.select("a[href]"):
            href = urljoin(BASE, a["href"])
            # Check for HTML pages
            if PROJ_PAGE_RE.search(href):
                html_pages.add(href)
            # Check for PDF files
            if SEP_PDF_RE.search(href):
                pdf_urls.add(href)
        time.sleep(0.25)

    # 2) FOMC calendars (2020+) - look for HTML pages
    print("Fetching FOMC calendar...")
    cal = fetch_soup(CAL_URL)
    for a in cal.select("a[href]"):
        href = urljoin(BASE, a["href"])
        if PROJ_PAGE_RE.search(href):
            html_pages.add(href)

    return sorted(html_pages), sorted(pdf_urls)


def main():
    html_output = Path("data_out/sep_page_urls.txt")
    pdf_output = Path("data_out/sep_pdf_urls.txt")
    html_output.parent.mkdir(parents=True, exist_ok=True)

    print("Discovering SEP projection materials...")
    html_pages, pdf_urls = discover_sep_urls()

    # Save HTML page URLs
    html_output.write_text("\n".join(html_pages) + "\n")
    print(f"\nHTML pages (2020+): {len(html_pages)}")
    print(f"  Saved to {html_output}")
    if html_pages:
        dates = [PROJ_PAGE_RE.search(p).group(1) for p in html_pages]
        print(f"  Date range: {min(dates)} to {max(dates)}")

    # Save PDF URLs
    pdf_output.write_text("\n".join(pdf_urls) + "\n")
    print(f"\nPDF files (2012-2019): {len(pdf_urls)}")
    print(f"  Saved to {pdf_output}")
    if pdf_urls:
        dates = [SEP_PDF_RE.search(p).group(1) for p in pdf_urls]
        print(f"  Date range: {min(dates)} to {max(dates)}")


if __name__ == "__main__":
    main()
