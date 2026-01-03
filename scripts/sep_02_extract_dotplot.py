#!/usr/bin/env python3
"""
Extract Figure 2 dot plot data from FOMC SEP projection pages.

Reads: data_out/sep_page_urls.txt
Outputs:
  - data_out/sep_dots.csv (individual dot values)
  - data_out/sep_summary.csv (percentile summary by meeting/horizon)
"""

import io
import re
import time
import warnings
from pathlib import Path
from typing import Optional, Tuple, List

import numpy as np
import pandas as pd
import requests


# Match patterns for Figure 2 (federal funds rate dot plot)
FIG2_MATCH_PATTERNS = [
    "Midpoint of target range",
    "target range or target level",
    "federal funds rate",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; sep-dotplot-scraper/1.0)",
}

# Regex to extract meeting date from URL
PROJ_PAGE_RE = re.compile(r"/monetarypolicy/fomcprojtabl(\d{8})\.htm$", re.I)


def meeting_date_from_url(url: str) -> pd.Timestamp:
    """Extract meeting date from fomcprojtabl URL."""
    m = PROJ_PAGE_RE.search(url)
    if not m:
        raise ValueError(f"Not a projtabl URL: {url}")
    yyyymmdd = m.group(1)
    return pd.to_datetime(yyyymmdd, format="%Y%m%d")


def fetch_html(url: str, timeout: int = 60) -> str:
    """Fetch URL with proper headers and return HTML content."""
    r = requests.get(url, headers=HEADERS, timeout=timeout)
    r.raise_for_status()
    return r.text


def extract_dotplot_table(proj_url: str) -> Optional[pd.DataFrame]:
    """
    Extract Figure 2 dot-plot count table from a projection materials page.
    Uses pandas.read_html and matches on common Figure 2 phrases.
    """
    try:
        html = fetch_html(proj_url)
    except Exception as e:
        warnings.warn(f"Failed to fetch {proj_url}: {e}")
        return None

    for pat in FIG2_MATCH_PATTERNS:
        try:
            tables = pd.read_html(io.StringIO(html), match=pat)
            if tables:
                return tables[0]
        except ValueError:
            continue
        except Exception as e:
            warnings.warn(f"read_html error on {proj_url} with match={pat}: {e}")
            continue
    return None


def clean_dotplot_counts(raw: pd.DataFrame) -> pd.DataFrame:
    """
    Clean the Figure 2 table into long format:
      rate (float), horizon (str), count (int)
    """
    df = raw.copy()

    # Normalize column names
    df.columns = [str(c).strip() for c in df.columns]

    # First column should be rate levels
    rate_col = df.columns[0]
    df = df.rename(columns={rate_col: "rate"})

    # Coerce rate to numeric
    df["rate"] = pd.to_numeric(df["rate"], errors="coerce")
    df = df.dropna(subset=["rate"])

    # Melt horizons (all columns except rate)
    horizons = [c for c in df.columns if c != "rate"]
    long = df.melt(id_vars=["rate"], value_vars=horizons, var_name="horizon", value_name="count")

    # Clean counts: blanks -> 0
    long["count"] = pd.to_numeric(long["count"], errors="coerce").fillna(0).astype(int)

    # Drop zero-count rows
    long = long[long["count"] > 0].copy()

    # Clean horizon labels
    long["horizon"] = long["horizon"].astype(str).str.strip()

    return long.sort_values(["horizon", "rate"], ascending=[True, True]).reset_index(drop=True)


def expand_to_dots(counts_long: pd.DataFrame) -> pd.DataFrame:
    """
    Expand (rate, horizon, count) into individual dots.
    Returns DataFrame with columns: horizon, dot_value
    """
    rows = []
    for _, r in counts_long.iterrows():
        rows.append(pd.DataFrame({
            "horizon": [r["horizon"]] * r["count"],
            "dot_value": [float(r["rate"])] * r["count"],
        }))
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(columns=["horizon", "dot_value"])


def summarize_dots(dots: pd.DataFrame) -> pd.DataFrame:
    """
    Compute n / p25 / p50 / p75 for each horizon.
    Returns wide format with columns: horizon, n, p25, p50, p75
    """
    def agg_func(s):
        return pd.Series({
            "n": int(len(s)),
            "p25": float(np.quantile(s.values, 0.25)),
            "p50": float(np.quantile(s.values, 0.50)),
            "p75": float(np.quantile(s.values, 0.75)),
        })

    out = dots.groupby("horizon")["dot_value"].apply(agg_func).unstack().reset_index()
    return out


def build_sep_dotplot_panel(proj_urls: List[str]) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Process all SEP pages and build dot panel + summary panel.

    Returns:
      dots_panel: meeting_date, horizon, dot_value
      summary_panel: meeting_date, horizon, n, p25, p50, p75
    """
    dots_all = []
    summ_all = []

    for i, url in enumerate(proj_urls, 1):
        dt = meeting_date_from_url(url)
        print(f"  [{i}/{len(proj_urls)}] {dt.strftime('%Y-%m-%d')}: {url}")

        raw = extract_dotplot_table(url)
        if raw is None:
            warnings.warn(f"Could not find Figure 2 table on {url}")
            continue

        counts = clean_dotplot_counts(raw)
        dots = expand_to_dots(counts)
        if dots.empty:
            continue

        dots.insert(0, "meeting_date", dt)
        summ = summarize_dots(dots)
        summ.insert(0, "meeting_date", dt)

        dots_all.append(dots)
        summ_all.append(summ)

        # Be polite to the Fed
        time.sleep(0.35)

    dots_panel = pd.concat(dots_all, ignore_index=True) if dots_all else pd.DataFrame()
    summary_panel = pd.concat(summ_all, ignore_index=True) if summ_all else pd.DataFrame()

    return dots_panel, summary_panel


def main():
    urls_path = Path("data_out/sep_page_urls.txt")
    if not urls_path.exists():
        print(f"Error: {urls_path} not found. Run sep_01_discover_pages.py first.")
        return

    urls = [line.strip() for line in urls_path.read_text().splitlines() if line.strip()]
    print(f"Processing {len(urls)} SEP pages...")

    dots_panel, summary_panel = build_sep_dotplot_panel(urls)

    # Save outputs
    dots_path = Path("data_out/sep_dots.csv")
    summary_path = Path("data_out/sep_summary.csv")

    dots_panel.to_csv(dots_path, index=False)
    summary_panel.to_csv(summary_path, index=False)

    print(f"\nSaved {len(dots_panel)} dots to {dots_path}")
    print(f"Saved {len(summary_panel)} summary rows to {summary_path}")

    # Show stats for longer-run horizon
    if not summary_panel.empty and "horizon" in summary_panel.columns:
        lr = summary_panel[summary_panel["horizon"].str.lower().str.contains("longer")]
        if not lr.empty:
            print(f"\nLonger-run horizon: {len(lr)} meetings")
            print(f"  Date range: {lr['meeting_date'].min()} to {lr['meeting_date'].max()}")
            print(f"  Median range: {lr['p50'].min():.2f}% to {lr['p50'].max():.2f}%")


if __name__ == "__main__":
    main()
