"""
Download survey files (XLSX and PDF) from the NY Fed website.

This module handles:
- Downloading files with retries and error handling
- Caching to avoid re-downloading existing files
- Progress reporting
"""

import hashlib
import time
from pathlib import Path
from typing import List, Tuple, Optional

import requests
from tqdm import tqdm

from .utils import (
    logger,
    SurveyLink,
    SurveyMeeting,
    get_local_path,
)


# Download settings
DEFAULT_TIMEOUT = 60
MAX_RETRIES = 3
RETRY_DELAY = 2


def calculate_file_hash(filepath: Path, chunk_size: int = 8192) -> str:
    """Calculate MD5 hash of a file."""
    hasher = hashlib.md5()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def download_file(
    url: str,
    dest_path: Path,
    timeout: int = DEFAULT_TIMEOUT,
    force: bool = False,
) -> bool:
    """
    Download a file from a URL.
    
    Args:
        url: URL to download from
        dest_path: Local path to save the file
        timeout: Request timeout in seconds
        force: If True, re-download even if file exists
    
    Returns:
        True if download was successful, False otherwise
    """
    # Check if file already exists
    if dest_path.exists() and not force:
        logger.debug(f"File already exists, skipping: {dest_path.name}")
        return True
    
    # Ensure parent directory exists
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Accept": "*/*",
    }
    
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            logger.info(f"Downloading ({attempt}/{MAX_RETRIES}): {url}")
            
            response = requests.get(
                url,
                headers=headers,
                timeout=timeout,
                stream=True,
            )
            response.raise_for_status()
            
            # Get content length for progress bar
            total_size = int(response.headers.get("content-length", 0))
            
            # Write to file with progress
            with open(dest_path, "wb") as f:
                if total_size > 0:
                    with tqdm(
                        total=total_size,
                        unit="B",
                        unit_scale=True,
                        desc=dest_path.name[:30],
                        leave=False,
                    ) as pbar:
                        for chunk in response.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)
                                pbar.update(len(chunk))
                else:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
            
            logger.info(f"Downloaded: {dest_path.name} ({dest_path.stat().st_size} bytes)")
            return True
            
        except requests.RequestException as e:
            logger.warning(f"Download failed (attempt {attempt}): {e}")
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY * attempt)
            else:
                logger.error(f"Failed to download after {MAX_RETRIES} attempts: {url}")
                return False
    
    return False


def download_meeting_files(
    meeting: SurveyMeeting,
    data_dir: Path,
    prefer_xlsx: bool = True,
    force: bool = False,
) -> List[Tuple[SurveyLink, Path]]:
    """
    Download files for a meeting, preferring XLSX over PDF.
    
    Args:
        meeting: SurveyMeeting object with links
        data_dir: Directory to save files
        prefer_xlsx: If True, only download PDFs when no XLSX available
        force: If True, re-download existing files
    
    Returns:
        List of (link, local_path) tuples for successfully downloaded files
    """
    downloaded = []
    
    xlsx_links = meeting.get_xlsx_links()
    pdf_links = meeting.get_pdf_links()
    
    # Determine which files to download
    links_to_download = []
    
    if xlsx_links:
        links_to_download.extend(xlsx_links)
    elif pdf_links and prefer_xlsx:
        # No XLSX, fall back to PDFs
        links_to_download.extend(pdf_links)
    
    if not prefer_xlsx:
        # Download all PDFs too
        links_to_download.extend(pdf_links)
    
    # Remove duplicates (same URL)
    seen_urls = set()
    unique_links = []
    for link in links_to_download:
        if link.url not in seen_urls:
            seen_urls.add(link.url)
            unique_links.append(link)
    
    # Download each file
    for link in unique_links:
        local_path = get_local_path(link.url, data_dir)
        
        if download_file(link.url, local_path, force=force):
            downloaded.append((link, local_path))
        else:
            logger.error(f"Failed to download: {link.url}")
    
    return downloaded


def download_all_meetings(
    meetings: List[SurveyMeeting],
    data_dir: Path,
    prefer_xlsx: bool = True,
    force: bool = False,
    max_files: Optional[int] = None,
) -> List[Tuple[SurveyMeeting, SurveyLink, Path]]:
    """
    Download files for all meetings.
    
    Args:
        meetings: List of SurveyMeeting objects
        data_dir: Directory to save files
        prefer_xlsx: If True, only download PDFs when no XLSX available
        force: If True, re-download existing files
        max_files: Maximum number of files to download (for testing)
    
    Returns:
        List of (meeting, link, local_path) tuples for successfully downloaded files
    """
    logger.info(f"Downloading files for {len(meetings)} meetings to {data_dir}")
    
    all_downloaded = []
    file_count = 0
    
    for meeting in tqdm(meetings, desc="Meetings", unit="meeting"):
        if max_files and file_count >= max_files:
            logger.info(f"Reached max files limit: {max_files}")
            break
        
        downloaded = download_meeting_files(
            meeting,
            data_dir,
            prefer_xlsx=prefer_xlsx,
            force=force,
        )
        
        for link, local_path in downloaded:
            all_downloaded.append((meeting, link, local_path))
            file_count += 1
            
            if max_files and file_count >= max_files:
                break
    
    logger.info(f"Downloaded {len(all_downloaded)} files")
    return all_downloaded


if __name__ == "__main__":
    # Test download functionality
    from pathlib import Path
    
    data_dir = Path("data_raw")
    data_dir.mkdir(exist_ok=True)
    
    # Test with a known file URL
    test_url = "https://www.newyorkfed.org/medialibrary/media/markets/survey/2024/dec2024results_sme.pdf"
    test_path = data_dir / "test_download.pdf"
    
    success = download_file(test_url, test_path, force=True)
    print(f"Download successful: {success}")
    
    if test_path.exists():
        print(f"File size: {test_path.stat().st_size} bytes")

