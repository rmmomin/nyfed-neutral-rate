#!/usr/bin/env python3
"""
Pull the federal funds target range from FRED and compare its midpoint with
longer-run neutral rate expectations.

Reads:
  - FRED_API_KEY from environment or .env
  - data_out/nyfed_ff_longrun_percentiles.csv

Outputs:
  - data_out/fed_target_midpoint_vs_neutral.csv
  - data_out/fed_target_midpoint_vs_neutral_metadata.csv
  - data_out/fed_target_midpoint_vs_neutral.png
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
FRED_SERIES = {
    "DFEDTARL": {
        "column": "target_lower",
        "label": "Federal Funds Target Range Lower Limit",
    },
    "DFEDTARU": {
        "column": "target_upper",
        "label": "Federal Funds Target Range Upper Limit",
    },
    "FEDTARMDLR": {
        "column": "sep_longrun_median",
        "label": "SEP Longer-Run Fed Funds Median",
    },
}
NYFED_PANELS = {
    "SPD": {
        "column": "nyfed_spd_median",
        "label": "NY Fed SPD Median",
        "color": "#1a5f7a",
        "marker": "o",
    },
    "SMP": {
        "column": "nyfed_smp_median",
        "label": "NY Fed SMP Median",
        "color": "#2a9d8f",
        "marker": "v",
    },
    "Combined": {
        "column": "nyfed_combined_median",
        "label": "NY Fed Combined Median",
        "color": "#f4a261",
        "marker": "s",
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


def fetch_fred_series(series_id: str, api_key: str, observation_start: str) -> pd.DataFrame:
    data = fred_get(
        "series/observations",
        api_key,
        series_id=series_id,
        observation_start=observation_start,
    )
    observations = data.get("observations", [])
    df = pd.DataFrame(observations)
    if df.empty:
        return pd.DataFrame(columns=["date", FRED_SERIES[series_id]["column"]])

    column = FRED_SERIES[series_id]["column"]
    df = df[["date", "value"]].copy()
    df["date"] = pd.to_datetime(df["date"])
    df[column] = pd.to_numeric(df["value"], errors="coerce")
    df = df.drop(columns=["value"])
    return df.dropna(subset=[column])


def fetch_fred_metadata(series_ids: Iterable[str], api_key: str) -> pd.DataFrame:
    rows: List[Dict] = []
    for series_id in series_ids:
        data = fred_get("series", api_key, series_id=series_id)
        seriess = data.get("seriess", [])
        if not seriess:
            continue
        series = seriess[0]
        rows.append({
            "series_id": series_id,
            "label": FRED_SERIES[series_id]["label"],
            "column": FRED_SERIES[series_id]["column"],
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


def build_fred_panel(api_key: str, observation_start: str) -> pd.DataFrame:
    panel = None
    for series_id in FRED_SERIES:
        observations = fetch_fred_series(series_id, api_key, observation_start)
        panel = observations if panel is None else panel.merge(observations, on="date", how="outer")

    if panel is None or panel.empty:
        raise RuntimeError("No FRED observations returned for the requested series.")

    panel = panel.sort_values("date")
    panel["target_midpoint"] = (panel["target_lower"] + panel["target_upper"]) / 2
    return panel


def build_nyfed_panel(nyfed_path: Path, observation_start: str) -> pd.DataFrame:
    nyfed = pd.read_csv(nyfed_path, parse_dates=["survey_date"])
    nyfed = nyfed[
        nyfed["panel"].isin(NYFED_PANELS.keys())
        & nyfed["pctl50"].notna()
        & (nyfed["survey_date"] >= pd.Timestamp(observation_start))
    ].copy()
    if nyfed.empty:
        return pd.DataFrame(columns=["date"] + [cfg["column"] for cfg in NYFED_PANELS.values()])

    nyfed["column"] = nyfed["panel"].map({panel: cfg["column"] for panel, cfg in NYFED_PANELS.items()})
    pivot = nyfed.pivot_table(
        index="survey_date",
        columns="column",
        values="pctl50",
        aggfunc="last",
    ).reset_index()
    pivot = pivot.rename(columns={"survey_date": "date"})
    return pivot.sort_values("date")


def build_comparison_panel(fred: pd.DataFrame, nyfed: pd.DataFrame) -> pd.DataFrame:
    comparison = fred.merge(nyfed, on="date", how="outer")
    ordered_columns = [
        "date",
        "target_lower",
        "target_upper",
        "target_midpoint",
        "sep_longrun_median",
        "nyfed_spd_median",
        "nyfed_smp_median",
        "nyfed_combined_median",
    ]
    for column in ordered_columns:
        if column not in comparison.columns:
            comparison[column] = pd.NA
    return comparison[ordered_columns].sort_values("date")


def plot_comparison(comparison: pd.DataFrame, output_path: Path) -> None:
    fig, ax = plt.subplots(figsize=(14, 7), facecolor="white")
    ax.set_facecolor("white")

    target = comparison[comparison["target_midpoint"].notna()].copy()
    sep = comparison[comparison["sep_longrun_median"].notna()].copy()

    ax.plot(
        target["date"],
        target["target_midpoint"],
        color="#424242",
        linewidth=2.0,
        drawstyle="steps-post",
        label="Fed Funds Target Midpoint",
    )
    ax.plot(
        sep["date"],
        sep["sep_longrun_median"],
        color="#e63946",
        linewidth=2.4,
        marker="D",
        markersize=4,
        label="SEP Longer-Run Median",
    )

    for panel, cfg in NYFED_PANELS.items():
        panel_df = comparison[comparison[cfg["column"]].notna()].copy()
        if panel_df.empty:
            continue
        ax.plot(
            panel_df["date"],
            panel_df[cfg["column"]],
            color=cfg["color"],
            linewidth=1.8,
            marker=cfg["marker"],
            markersize=4,
            label=cfg["label"],
        )

    ax.set_xlabel("Date", fontsize=12, fontweight="bold")
    ax.set_ylabel("Federal Funds Rate (%)", fontsize=12, fontweight="bold")
    ax.set_title(
        "Fed Funds Target Midpoint vs Longer-Run Neutral Rate Expectations",
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

    value_columns = [
        "target_midpoint",
        "sep_longrun_median",
        "nyfed_spd_median",
        "nyfed_smp_median",
        "nyfed_combined_median",
    ]
    all_values = comparison[value_columns].stack().dropna()
    if not all_values.empty:
        ax.set_ylim(max(0, all_values.min() - 0.5), all_values.max() + 0.5)

    ax.legend(loc="upper left", framealpha=0.95, fontsize=9, ncol=2)
    add_chart_footer(
        fig,
        "Sources: FRED, Federal Reserve Bank of St. Louis; FOMC Summary of Economic "
        "Projections; NY Fed Survey of Primary Dealers and Survey of Market "
        "Participants; author's calculations.",
    )

    plt.tight_layout(rect=(0, 0.055, 1, 1))
    plt.savefig(output_path, dpi=150, facecolor="white", bbox_inches="tight")
    plt.close()


def main():
    parser = argparse.ArgumentParser(
        description="Compare fed funds target midpoint with longer-run neutral rate expectations."
    )
    parser.add_argument(
        "--start-date",
        default="2012-01-01",
        help="Earliest observation date to pull and plot.",
    )
    parser.add_argument(
        "--nyfed-csv",
        default="data_out/nyfed_ff_longrun_percentiles.csv",
        type=Path,
        help="NY Fed survey median CSV.",
    )
    parser.add_argument(
        "--output-csv",
        default="data_out/fed_target_midpoint_vs_neutral.csv",
        type=Path,
        help="Output CSV path for the comparison panel.",
    )
    parser.add_argument(
        "--metadata-csv",
        default="data_out/fed_target_midpoint_vs_neutral_metadata.csv",
        type=Path,
        help="Output CSV path for FRED series metadata.",
    )
    parser.add_argument(
        "--output-png",
        default="data_out/fed_target_midpoint_vs_neutral.png",
        type=Path,
        help="Output PNG path for the chart.",
    )
    args = parser.parse_args()

    api_key = get_fred_api_key()
    fred = build_fred_panel(api_key, args.start_date)
    nyfed = build_nyfed_panel(args.nyfed_csv, args.start_date)
    comparison = build_comparison_panel(fred, nyfed)
    metadata = fetch_fred_metadata(FRED_SERIES.keys(), api_key)

    args.output_csv.parent.mkdir(parents=True, exist_ok=True)
    comparison.to_csv(args.output_csv, index=False)
    metadata.to_csv(args.metadata_csv, index=False)
    plot_comparison(comparison, args.output_png)

    print(f"Saved {len(comparison)} rows to {args.output_csv}")
    print(f"Saved metadata to {args.metadata_csv}")
    print(f"Chart saved to {args.output_png}")
    print(
        "Date range: "
        f"{comparison['date'].min().strftime('%Y-%m-%d')} to "
        f"{comparison['date'].max().strftime('%Y-%m-%d')}"
    )
    print(
        "Target midpoint range: "
        f"{comparison['target_midpoint'].min():.2f}% to {comparison['target_midpoint'].max():.2f}%"
    )


if __name__ == "__main__":
    main()
