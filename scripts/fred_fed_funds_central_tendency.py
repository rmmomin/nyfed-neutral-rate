#!/usr/bin/env python3
"""
Pull FRED SEP longer-run fed funds rate median and central tendency series.

Reads:
  - FRED_API_KEY from environment or .env

Outputs:
  - data_out/fred_fed_funds_central_tendency.csv
  - data_out/fred_fed_funds_central_tendency_metadata.csv
  - data_out/fred_fed_funds_central_tendency.png
"""

import argparse
import os
import sys
from pathlib import Path
from typing import Dict, Iterable, List

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.chart_style import add_chart_footer


FRED_API_BASE = "https://api.stlouisfed.org/fred"
SERIES = {
    "FEDTARMDLR": {
        "column": "longrun_median",
        "label": "Longer-Run Median",
    },
    "FEDTARCTLLR": {
        "column": "central_tendency_low",
        "label": "Central Tendency Low",
    },
    "FEDTARCTMLR": {
        "column": "central_tendency_midpoint",
        "label": "Central Tendency Midpoint",
    },
    "FEDTARCTHLR": {
        "column": "central_tendency_high",
        "label": "Central Tendency High",
    },
}


def load_dotenv(path: Path = Path(".env")) -> None:
    """Load simple KEY=VALUE pairs from .env without overriding the shell."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def get_fred_api_key() -> str:
    load_dotenv()
    api_key = os.environ.get("FRED_API_KEY")
    if not api_key:
        raise RuntimeError("FRED_API_KEY is not set. Add it to .env or export it in the shell.")
    return api_key


def fred_get(endpoint: str, api_key: str, **params) -> Dict:
    request_params = {
        "api_key": api_key,
        "file_type": "json",
        **params,
    }
    response = requests.get(
        f"{FRED_API_BASE}/{endpoint}",
        params=request_params,
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()
    if "error_code" in data:
        raise RuntimeError(f"FRED API error {data['error_code']}: {data.get('error_message', '')}")
    return data


def fetch_series_observations(series_id: str, api_key: str) -> pd.DataFrame:
    data = fred_get("series/observations", api_key, series_id=series_id)
    observations = data.get("observations", [])
    df = pd.DataFrame(observations)
    if df.empty:
        return pd.DataFrame(columns=["date", SERIES[series_id]["column"]])

    column = SERIES[series_id]["column"]
    df = df[["date", "value"]].copy()
    df["date"] = pd.to_datetime(df["date"])
    df[column] = pd.to_numeric(df["value"], errors="coerce")
    df = df.drop(columns=["value"])
    return df.dropna(subset=[column])


def fetch_series_metadata(series_ids: Iterable[str], api_key: str) -> pd.DataFrame:
    rows: List[Dict] = []
    for series_id in series_ids:
        data = fred_get("series", api_key, series_id=series_id)
        seriess = data.get("seriess", [])
        if not seriess:
            continue
        series = seriess[0]
        rows.append({
            "series_id": series_id,
            "label": SERIES[series_id]["label"],
            "column": SERIES[series_id]["column"],
            "title": series.get("title"),
            "units": series.get("units"),
            "frequency": series.get("frequency"),
            "seasonal_adjustment": series.get("seasonal_adjustment"),
            "observation_start": series.get("observation_start"),
            "observation_end": series.get("observation_end"),
            "last_updated": series.get("last_updated"),
            "notes": series.get("notes"),
        })
    return pd.DataFrame(rows)


def build_panel(api_key: str) -> pd.DataFrame:
    panel = None
    for series_id in SERIES:
        observations = fetch_series_observations(series_id, api_key)
        panel = observations if panel is None else panel.merge(observations, on="date", how="outer")

    if panel is None or panel.empty:
        raise RuntimeError("No FRED observations returned for the requested series.")

    panel = panel.sort_values("date")
    return panel


def plot_central_tendency(df: pd.DataFrame, output_path: Path) -> None:
    fig, ax = plt.subplots(figsize=(14, 7), facecolor="white")
    ax.set_facecolor("white")

    color_band = "#b8d6df"
    color_mid = "#1a5f7a"
    color_median = "#e63946"

    ax.fill_between(
        df["date"],
        df["central_tendency_low"],
        df["central_tendency_high"],
        color=color_band,
        alpha=0.45,
        label="Central Tendency Bounds",
    )
    ax.plot(
        df["date"],
        df["longrun_median"],
        color=color_median,
        linewidth=2.7,
        marker="o",
        markersize=4,
        label="Longer-Run Median",
    )
    ax.plot(
        df["date"],
        df["central_tendency_midpoint"],
        color=color_mid,
        linewidth=2.0,
        marker="D",
        markersize=3.5,
        label="Central Tendency Midpoint",
    )

    ax.set_xlabel("SEP Release Date", fontsize=12, fontweight="bold")
    ax.set_ylabel("Federal Funds Rate (%)", fontsize=12, fontweight="bold")
    ax.set_title(
        "FOMC SEP: Longer-Run Fed Funds Rate Estimate",
        fontsize=16,
        fontweight="bold",
        pad=15,
    )

    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax.xaxis.set_major_locator(mdates.YearLocator())
    plt.xticks(rotation=45, ha="right")

    ax.grid(True, alpha=0.3, linestyle="-", linewidth=0.5)
    ax.set_axisbelow(True)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    all_values = df[[
        "longrun_median",
        "central_tendency_low",
        "central_tendency_midpoint",
        "central_tendency_high",
    ]].stack().dropna()
    if not all_values.empty:
        ax.set_ylim(max(0, all_values.min() - 0.25), all_values.max() + 0.25)

    ax.legend(loc="upper right", framealpha=0.95, fontsize=10)
    add_chart_footer(
        fig,
        "Source: FRED, Federal Reserve Bank of St. Louis; FOMC Summary of Economic "
        "Projections; author's calculations.",
    )

    plt.tight_layout(rect=(0, 0.055, 1, 1))
    plt.savefig(output_path, dpi=150, facecolor="white", bbox_inches="tight")
    plt.close()


def main():
    parser = argparse.ArgumentParser(
        description="Pull and plot FRED SEP longer-run fed funds rate series."
    )
    parser.add_argument(
        "--output-csv",
        default="data_out/fred_fed_funds_central_tendency.csv",
        type=Path,
        help="Output CSV path for the observation panel.",
    )
    parser.add_argument(
        "--metadata-csv",
        default="data_out/fred_fed_funds_central_tendency_metadata.csv",
        type=Path,
        help="Output CSV path for FRED series metadata.",
    )
    parser.add_argument(
        "--output-png",
        default="data_out/fred_fed_funds_central_tendency.png",
        type=Path,
        help="Output PNG path for the chart.",
    )
    args = parser.parse_args()

    api_key = get_fred_api_key()
    panel = build_panel(api_key)
    metadata = fetch_series_metadata(SERIES.keys(), api_key)

    args.output_csv.parent.mkdir(parents=True, exist_ok=True)
    panel.to_csv(args.output_csv, index=False)
    metadata.to_csv(args.metadata_csv, index=False)
    plot_central_tendency(panel, args.output_png)

    print(f"Saved {len(panel)} observations to {args.output_csv}")
    print(f"Saved metadata to {args.metadata_csv}")
    print(f"Chart saved to {args.output_png}")
    print(
        "Date range: "
        f"{panel['date'].min().strftime('%Y-%m-%d')} to {panel['date'].max().strftime('%Y-%m-%d')}"
    )


if __name__ == "__main__":
    main()
