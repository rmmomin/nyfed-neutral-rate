#!/usr/bin/env python3
"""
Download historical SEP PDFs (2012-2019) from Federal Reserve website.

Reads: data_out/sep_pdf_urls.txt
Outputs: data_raw/sep/*.pdf
"""

import time
from pathlib import Path
from urllib.parse import urlparse

import requests
from tqdm import tqdm


HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; sep-dotplot-scraper/1.0)",
}


def download_pdf(url: str, output_dir: Path, timeout: int = 60) -> Path:
    """Download a PDF file to output_dir. Returns path to downloaded file."""
    filename = Path(urlparse(url).path).name
    output_path = output_dir / filename

    if output_path.exists():
        return output_path  # Skip if already downloaded

    r = requests.get(url, headers=HEADERS, timeout=timeout)
    r.raise_for_status()

    output_path.write_bytes(r.content)
    return output_path


def main():
    urls_path = Path("data_out/sep_pdf_urls.txt")
    output_dir = Path("data_raw/sep")

    if not urls_path.exists():
        print(f"Error: {urls_path} not found. Run sep_01_discover_pages.py first.")
        return

    output_dir.mkdir(parents=True, exist_ok=True)

    urls = [line.strip() for line in urls_path.read_text().splitlines() if line.strip()]
    print(f"Found {len(urls)} PDF URLs to download")

    downloaded = 0
    skipped = 0

    for url in tqdm(urls, desc="Downloading PDFs"):
        output_path = output_dir / Path(urlparse(url).path).name

        if output_path.exists():
            skipped += 1
            continue

        try:
            download_pdf(url, output_dir)
            downloaded += 1
            time.sleep(0.35)  # Be polite
        except Exception as e:
            print(f"\nError downloading {url}: {e}")

    print(f"\nDownload complete:")
    print(f"  Downloaded: {downloaded}")
    print(f"  Skipped (existing): {skipped}")
    print(f"  Output directory: {output_dir}")


if __name__ == "__main__":
    main()
