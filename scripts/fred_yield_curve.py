#!/usr/bin/env python3
"""
Pull Treasury constant maturity yields from FRED and plot the yield curve.

Reads:
  - FRED_API_KEY from environment or .env

Outputs:
  - data_out/fred_yield_curve_history.csv
  - data_out/fred_yield_curve_latest.csv
  - data_out/fred_yield_curve_metadata.csv
  - data_out/fred_yield_curve.png
  - data_out/fred_yield_curve_latest_vs_2026-02-27.csv
  - data_out/fred_yield_curve_latest_vs_2026-02-27.png
"""

import argparse
import os
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import matplotlib.pyplot as plt
import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.chart_style import add_chart_footer


FRED_API_BASE = "https://api.stlouisfed.org/fred"
YIELD_SERIES = {
    "DGS1MO": {
        "column": "yield_1mo",
        "label": "1M",
        "maturity_years": 1 / 12,
    },
    "DGS3MO": {
        "column": "yield_3mo",
        "label": "3M",
        "maturity_years": 0.25,
    },
    "DGS6MO": {
        "column": "yield_6mo",
        "label": "6M",
        "maturity_years": 0.5,
    },
    "DGS1": {
        "column": "yield_1y",
        "label": "1Y",
        "maturity_years": 1,
    },
    "DGS2": {
        "column": "yield_2y",
        "label": "2Y",
        "maturity_years": 2,
    },
    "DGS3": {
        "column": "yield_3y",
        "label": "3Y",
        "maturity_years": 3,
    },
    "DGS5": {
        "column": "yield_5y",
        "label": "5Y",
        "maturity_years": 5,
    },
    "DGS7": {
        "column": "yield_7y",
        "label": "7Y",
        "maturity_years": 7,
    },
    "DGS10": {
        "column": "yield_10y",
        "label": "10Y",
        "maturity_years": 10,
    },
    "DGS20": {
        "column": "yield_20y",
        "label": "20Y",
        "maturity_years": 20,
    },
    "DGS30": {
        "column": "yield_30y",
        "label": "30Y",
        "maturity_years": 30,
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


def fetch_series_observations(
    series_id: str,
    api_key: str,
    observation_start: str,
) -> pd.DataFrame:
    data = fred_get(
        "series/observations",
        api_key,
        series_id=series_id,
        observation_start=observation_start,
    )
    observations = data.get("observations", [])
    df = pd.DataFrame(observations)
    if df.empty:
        return pd.DataFrame(columns=["date", YIELD_SERIES[series_id]["column"]])

    column = YIELD_SERIES[series_id]["column"]
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
            "label": YIELD_SERIES[series_id]["label"],
            "column": YIELD_SERIES[series_id]["column"],
            "maturity_years": YIELD_SERIES[series_id]["maturity_years"],
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


def build_yield_panel(api_key: str, observation_start: str) -> pd.DataFrame:
    panel: Optional[pd.DataFrame] = None
    for series_id in YIELD_SERIES:
        observations = fetch_series_observations(series_id, api_key, observation_start)
        panel = observations if panel is None else panel.merge(observations, on="date", how="outer")

    if panel is None or panel.empty:
        raise RuntimeError("No FRED observations returned for the requested series.")

    return panel.sort_values("date")


def select_curve_date(panel: pd.DataFrame, curve_date: Optional[str]) -> pd.Timestamp:
    yield_columns = [cfg["column"] for cfg in YIELD_SERIES.values()]

    if curve_date:
        requested = pd.Timestamp(curve_date)
        matching = panel[panel["date"] == requested]
        if matching.empty:
            raise RuntimeError(f"No yield curve observations found for {requested.date()}.")
        if matching[yield_columns].isna().any(axis=None):
            missing = [
                column
                for column in yield_columns
                if pd.isna(matching.iloc[0][column])
            ]
            raise RuntimeError(
                f"Requested curve date {requested.date()} has missing yields: {', '.join(missing)}"
            )
        return requested

    complete = panel.dropna(subset=yield_columns)
    if complete.empty:
        raise RuntimeError("No complete yield curve date found across all requested FRED series.")
    return complete["date"].max()


def build_curve(
    panel: pd.DataFrame,
    curve_date: pd.Timestamp,
    curve_label: str,
    curve_role: str,
    curve_order: int,
) -> pd.DataFrame:
    row = panel.loc[panel["date"] == curve_date].iloc[0]
    records: List[Dict] = []
    for series_id, cfg in YIELD_SERIES.items():
        records.append({
            "date": curve_date.date(),
            "curve_label": curve_label,
            "curve_role": curve_role,
            "curve_order": curve_order,
            "series_id": series_id,
            "maturity_label": cfg["label"],
            "maturity_years": cfg["maturity_years"],
            "yield_percent": row[cfg["column"]],
        })
    return pd.DataFrame(records)


def format_curve_date(curve_date: pd.Timestamp) -> str:
    return curve_date.strftime("%B %d, %Y").replace(" 0", " ")


def curve_spread_text(curve: pd.DataFrame) -> str:
    yields = curve.set_index("series_id")["yield_percent"]
    if not {"DGS2", "DGS10"}.issubset(yields.index):
        return ""
    two_ten = (yields["DGS10"] - yields["DGS2"]) * 100
    label = curve["curve_label"].iloc[0]
    return f"{label}: 10Y - 2Y = {two_ten:.0f} bps"


def plot_yield_curve(curves: pd.DataFrame, output_path: Path) -> None:
    fig, ax = plt.subplots(figsize=(12, 7), facecolor="white")
    ax.set_facecolor("white")

    curves = curves.sort_values(["curve_order", "maturity_years"]).copy()
    maturity_order = (
        curves[["series_id", "maturity_label", "maturity_years"]]
        .drop_duplicates()
        .sort_values("maturity_years")
        .reset_index(drop=True)
    )
    position_by_series = {
        row["series_id"]: idx
        for idx, row in maturity_order.iterrows()
    }
    curves["plot_position"] = curves["series_id"].map(position_by_series)
    curve_count = curves["curve_label"].nunique()

    styles = [
        {"color": "#1a5f7a", "marker": "o", "linewidth": 2.8},
        {"color": "#f4a261", "marker": "s", "linewidth": 2.4},
        {"color": "#2a9d8f", "marker": "v", "linewidth": 2.2},
    ]
    for idx, (curve_label, group) in enumerate(curves.groupby("curve_label", sort=False)):
        style = styles[idx % len(styles)]
        group = group.sort_values("plot_position")
        ax.plot(
            group["plot_position"],
            group["yield_percent"],
            color=style["color"],
            linewidth=style["linewidth"],
            marker=style["marker"],
            markersize=6,
            label=curve_label,
        )

        annotation_offset = 8 if idx == 0 else -14
        annotation_va = "bottom" if idx == 0 else "top"
        for _, row in group.iterrows():
            ax.annotate(
                f"{row['yield_percent']:.2f}%",
                (row["plot_position"], row["yield_percent"]),
                xytext=(0, annotation_offset),
                textcoords="offset points",
                ha="center",
                va=annotation_va,
                fontsize=7.5 if curve_count > 1 else 8.5,
                color=style["color"] if curve_count > 1 else "#263238",
            )

    ax.set_xticks(maturity_order.index)
    ax.set_xticklabels(maturity_order["maturity_label"])
    ax.set_xlabel("Maturity", fontsize=12, fontweight="bold")
    ax.set_ylabel("Yield (%)", fontsize=12, fontweight="bold")

    latest_date = pd.Timestamp(
        curves.loc[curves["curve_role"] == "latest", "date"].iloc[0]
    )
    comparison_dates = curves.loc[curves["curve_role"] == "comparison", "date"].unique()
    if len(comparison_dates):
        comparison_date = pd.Timestamp(comparison_dates[0])
        title = (
            "U.S. Treasury Yield Curve: "
            f"{format_curve_date(latest_date)} vs {format_curve_date(comparison_date)}"
        )
    else:
        title = f"U.S. Treasury Yield Curve as of {format_curve_date(latest_date)}"

    ax.set_title(title, fontsize=16, fontweight="bold", pad=15)

    spread_lines = [
        curve_spread_text(group)
        for _, group in curves.groupby("curve_label", sort=False)
    ]
    spread_lines = [line for line in spread_lines if line]
    if spread_lines:
        ax.text(
            0.01,
            0.95,
            "\n".join(spread_lines),
            transform=ax.transAxes,
            ha="left",
            va="top",
            fontsize=9.5,
            color="#333333",
            bbox={"facecolor": "white", "edgecolor": "#dddddd", "alpha": 0.9},
        )

    ax.grid(True, alpha=0.3, linestyle="-", linewidth=0.5)
    ax.set_axisbelow(True)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    y_min = curves["yield_percent"].min()
    y_max = curves["yield_percent"].max()
    y_pad = max(0.15, (y_max - y_min) * 0.25)
    ax.set_ylim(max(0, y_min - y_pad), y_max + y_pad)
    ax.legend(loc="lower right", framealpha=0.95, fontsize=10)

    add_chart_footer(
        fig,
        "Source: FRED, Federal Reserve Bank of St. Louis; U.S. Treasury constant "
        "maturity yields; author's calculations.",
    )

    plt.tight_layout(rect=(0, 0.055, 1, 1))
    plt.savefig(output_path, dpi=150, facecolor="white", bbox_inches="tight")
    plt.close()


def main():
    parser = argparse.ArgumentParser(
        description="Pull and plot Treasury constant maturity yields from FRED."
    )
    parser.add_argument(
        "--start-date",
        default="2001-07-31",
        help="Earliest observation date to pull.",
    )
    parser.add_argument(
        "--curve-date",
        default=None,
        help="Specific curve date to plot in YYYY-MM-DD format. Defaults to latest complete date.",
    )
    parser.add_argument(
        "--comparison-date",
        default=None,
        help="Optional second curve date to overlay in YYYY-MM-DD format.",
    )
    parser.add_argument(
        "--output-csv",
        default="data_out/fred_yield_curve_history.csv",
        type=Path,
        help="Output CSV path for the historical yield panel.",
    )
    parser.add_argument(
        "--latest-csv",
        "--curve-csv",
        dest="latest_csv",
        default="data_out/fred_yield_curve_latest.csv",
        type=Path,
        help="Output CSV path for the plotted yield curve or curves.",
    )
    parser.add_argument(
        "--metadata-csv",
        default="data_out/fred_yield_curve_metadata.csv",
        type=Path,
        help="Output CSV path for FRED series metadata.",
    )
    parser.add_argument(
        "--output-png",
        default="data_out/fred_yield_curve.png",
        type=Path,
        help="Output PNG path for the chart.",
    )
    args = parser.parse_args()

    api_key = get_fred_api_key()
    panel = build_yield_panel(api_key, args.start_date)
    metadata = fetch_series_metadata(YIELD_SERIES.keys(), api_key)
    curve_date = select_curve_date(panel, args.curve_date)
    curve_label = (
        f"Latest ({curve_date.strftime('%Y-%m-%d')})"
        if args.curve_date is None
        else f"Selected ({curve_date.strftime('%Y-%m-%d')})"
    )
    curves = [
        build_curve(
            panel,
            curve_date,
            curve_label,
            "latest",
            0,
        )
    ]
    comparison_date = None
    if args.comparison_date:
        comparison_date = select_curve_date(panel, args.comparison_date)
        curves.append(
            build_curve(
                panel,
                comparison_date,
                comparison_date.strftime("%Y-%m-%d"),
                "comparison",
                1,
            )
        )
    curve = pd.concat(curves, ignore_index=True)

    args.output_csv.parent.mkdir(parents=True, exist_ok=True)
    panel.to_csv(args.output_csv, index=False)
    curve.to_csv(args.latest_csv, index=False)
    metadata.to_csv(args.metadata_csv, index=False)
    plot_yield_curve(curve, args.output_png)

    print(f"Saved {len(panel)} historical rows to {args.output_csv}")
    print(f"Saved plotted curve data to {args.latest_csv}")
    print(f"Saved metadata to {args.metadata_csv}")
    print(f"Chart saved to {args.output_png}")
    print(f"Curve date: {curve_date.strftime('%Y-%m-%d')}")
    if comparison_date is not None:
        print(f"Comparison date: {comparison_date.strftime('%Y-%m-%d')}")


if __name__ == "__main__":
    main()
