#!/usr/bin/env python3
"""
Analyze how closely NY Fed longer-run fed funds survey medians are anchored to
the latest SEP longer-run median available before survey responses were due.

Reads:
  - data_out/nyfed_ff_longrun_percentiles.csv
  - data_out/fred_fed_funds_central_tendency.csv
  - data_out/fed_target_midpoint_vs_neutral.csv

Outputs:
  - data_out/nyfed_sep_anchor_analysis.csv
  - data_out/nyfed_sep_anchor_summary.csv
  - data_out/nyfed_sep_anchor_regressions.csv
  - data_out/nyfed_sep_anchor_analysis.png
"""

import argparse
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.chart_style import add_chart_footer


PANEL_ORDER = ["SPD", "SMP", "Combined"]
PANEL_LABELS = {
    "SPD": "NY Fed SPD",
    "SMP": "NY Fed SMP",
    "Combined": "NY Fed Combined",
}
PANEL_COLORS = {
    "SPD": "#1a5f7a",
    "SMP": "#2a9d8f",
    "Combined": "#f4a261",
}
PANEL_MARKERS = {
    "SPD": "o",
    "SMP": "v",
    "Combined": "s",
}


def ols(y: pd.Series, x: pd.DataFrame) -> Tuple[pd.Series, float, int]:
    """Return OLS coefficients, R-squared, and observation count."""
    data = pd.concat([y.rename("y"), x], axis=1).dropna()
    if data.empty:
        return pd.Series(dtype=float), np.nan, 0

    y_values = data["y"].astype(float).to_numpy()
    x_values = data.drop(columns=["y"]).astype(float)
    design = np.column_stack([np.ones(len(x_values)), x_values.to_numpy()])
    terms = ["intercept"] + list(x_values.columns)

    beta = np.linalg.lstsq(design, y_values, rcond=None)[0]
    fitted = design @ beta
    residual_ss = np.square(y_values - fitted).sum()
    total_ss = np.square(y_values - y_values.mean()).sum()
    r_squared = 1 - residual_ss / total_ss if total_ss else np.nan
    return pd.Series(beta, index=terms), r_squared, len(data)


def read_inputs(
    nyfed_path: Path,
    sep_path: Path,
    target_path: Path,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    market = pd.read_csv(
        nyfed_path,
        parse_dates=["survey_date", "distributed_date", "received_by_date"],
    )
    sep = pd.read_csv(sep_path, parse_dates=["date"])
    target = pd.read_csv(target_path, parse_dates=["date"])

    sep = sep[["date", "longrun_median"]].dropna().rename(
        columns={"date": "sep_release_date", "longrun_median": "sep_longrun_median"}
    )
    target = target[["date", "target_midpoint"]].dropna().rename(
        columns={"date": "target_date"}
    )
    return market, sep, target


def build_anchor_panel(
    market: pd.DataFrame,
    sep: pd.DataFrame,
    target: pd.DataFrame,
    allow_same_day_sep: bool,
) -> pd.DataFrame:
    rows = market[
        market["panel"].isin(PANEL_ORDER)
        & market["pctl50"].notna()
        & market["received_by_date"].notna()
    ].copy()
    rows = rows.sort_values(["received_by_date", "survey_date", "panel"])

    aligned = pd.merge_asof(
        rows,
        sep.sort_values("sep_release_date"),
        left_on="received_by_date",
        right_on="sep_release_date",
        direction="backward",
        allow_exact_matches=allow_same_day_sep,
    )
    aligned = pd.merge_asof(
        aligned.sort_values("received_by_date"),
        target.sort_values("target_date"),
        left_on="received_by_date",
        right_on="target_date",
        direction="backward",
    )

    aligned = aligned.dropna(subset=["sep_longrun_median", "target_midpoint"]).copy()
    aligned["market_median"] = aligned["pctl50"]
    aligned["market_minus_sep_pp"] = aligned["market_median"] - aligned["sep_longrun_median"]
    aligned["market_minus_sep_bps"] = (aligned["market_minus_sep_pp"] * 100).round(1)
    aligned["target_minus_sep_pp"] = aligned["target_midpoint"] - aligned["sep_longrun_median"]
    aligned["target_minus_sep_bps"] = (aligned["target_minus_sep_pp"] * 100).round(1)
    aligned["market_minus_target_bps"] = (
        (aligned["market_median"] - aligned["target_midpoint"]) * 100
    ).round(1)
    aligned["days_since_sep_release"] = (
        aligned["received_by_date"] - aligned["sep_release_date"]
    ).dt.days

    output_columns = [
        "survey_date",
        "distributed_date",
        "received_by_date",
        "panel",
        "market_median",
        "sep_release_date",
        "sep_longrun_median",
        "target_date",
        "target_midpoint",
        "market_minus_sep_pp",
        "market_minus_sep_bps",
        "target_minus_sep_pp",
        "target_minus_sep_bps",
        "market_minus_target_bps",
        "days_since_sep_release",
        "source",
        "local_path",
        "receipt_source_file",
    ]
    return aligned[output_columns].sort_values(["received_by_date", "panel"])


def build_summary(panel: pd.DataFrame) -> pd.DataFrame:
    rows: List[Dict] = []
    groups: List[Tuple[str, pd.DataFrame]] = [("All", panel)]
    groups.extend((panel_name, panel[panel["panel"] == panel_name]) for panel_name in PANEL_ORDER)

    for name, group in groups:
        if group.empty:
            continue
        gap = group["market_minus_sep_bps"]
        rows.append({
            "sample": name,
            "n": len(group),
            "first_received_by_date": group["received_by_date"].min().date(),
            "last_received_by_date": group["received_by_date"].max().date(),
            "mean_gap_bps": round(gap.mean(), 1),
            "median_gap_bps": round(gap.median(), 1),
            "mean_abs_gap_bps": round(gap.abs().mean(), 1),
            "median_abs_gap_bps": round(gap.abs().median(), 1),
            "rmse_gap_bps": round(np.sqrt(np.square(gap).mean()), 1),
            "within_25bp_share": round((gap.abs() <= 25).mean(), 3),
            "within_50bp_share": round((gap.abs() <= 50).mean(), 3),
            "corr_market_sep": round(group[["market_median", "sep_longrun_median"]].corr().iloc[0, 1], 3),
            "corr_gap_target_gap": round(
                group[["market_minus_sep_bps", "target_minus_sep_bps"]].corr().iloc[0, 1],
                3,
            ),
            "avg_days_since_sep_release": round(group["days_since_sep_release"].mean(), 1),
        })
    return pd.DataFrame(rows)


def add_regression_row(
    rows: List[Dict],
    sample: str,
    model: str,
    y: pd.Series,
    x: pd.DataFrame,
) -> None:
    coefficients, r_squared, n_obs = ols(y, x)
    row = {
        "sample": sample,
        "model": model,
        "n": n_obs,
        "r_squared": round(r_squared, 3) if pd.notna(r_squared) else pd.NA,
    }
    for term, value in coefficients.items():
        row[term] = round(value, 4)
    rows.append(row)


def build_regressions(panel: pd.DataFrame) -> pd.DataFrame:
    rows: List[Dict] = []
    samples: List[Tuple[str, pd.DataFrame]] = [("All", panel)]
    samples.extend((panel_name, panel[panel["panel"] == panel_name]) for panel_name in PANEL_ORDER)

    for sample, group in samples:
        if group.empty:
            continue
        add_regression_row(
            rows,
            sample,
            "market_median_on_sep",
            group["market_median"],
            group[["sep_longrun_median"]],
        )
        add_regression_row(
            rows,
            sample,
            "market_median_on_sep_and_target",
            group["market_median"],
            group[["sep_longrun_median", "target_midpoint"]],
        )
        add_regression_row(
            rows,
            sample,
            "market_minus_sep_bps_on_target_minus_sep_bps",
            group["market_minus_sep_bps"],
            group[["target_minus_sep_bps"]],
        )

    panel_fe = panel.copy()
    for panel_name in ["Combined", "SMP"]:
        panel_fe[f"panel_fe_{panel_name.lower()}"] = (
            panel_fe["panel"] == panel_name
        ).astype(float)
    add_regression_row(
        rows,
        "All",
        "market_median_on_sep_target_panel_fe",
        panel_fe["market_median"],
        panel_fe[[
            "sep_longrun_median",
            "target_midpoint",
            "panel_fe_combined",
            "panel_fe_smp",
        ]],
    )
    add_regression_row(
        rows,
        "All",
        "market_minus_sep_bps_on_target_minus_sep_bps_panel_fe",
        panel_fe["market_minus_sep_bps"],
        panel_fe[["target_minus_sep_bps", "panel_fe_combined", "panel_fe_smp"]],
    )

    return pd.DataFrame(rows)


def fit_line(group: pd.DataFrame) -> Tuple[float, float]:
    coefficients, _, _ = ols(
        group["market_minus_sep_bps"],
        group[["target_minus_sep_bps"]],
    )
    return coefficients.get("intercept", np.nan), coefficients.get("target_minus_sep_bps", np.nan)


def plot_anchor_analysis(panel: pd.DataFrame, output_path: Path) -> None:
    fig, (ax_left, ax_right) = plt.subplots(
        1,
        2,
        figsize=(15, 7),
        facecolor="white",
    )
    for ax in (ax_left, ax_right):
        ax.set_facecolor("white")
        ax.grid(True, alpha=0.3, linestyle="-", linewidth=0.5)
        ax.set_axisbelow(True)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)

    for panel_name in PANEL_ORDER:
        group = panel[panel["panel"] == panel_name]
        if group.empty:
            continue
        ax_left.scatter(
            group["sep_longrun_median"],
            group["market_median"],
            s=42,
            color=PANEL_COLORS[panel_name],
            marker=PANEL_MARKERS[panel_name],
            edgecolors="white",
            linewidths=0.5,
            alpha=0.85,
            label=PANEL_LABELS[panel_name],
        )
        ax_right.scatter(
            group["target_minus_sep_bps"],
            group["market_minus_sep_bps"],
            s=42,
            color=PANEL_COLORS[panel_name],
            marker=PANEL_MARKERS[panel_name],
            edgecolors="white",
            linewidths=0.5,
            alpha=0.85,
            label=PANEL_LABELS[panel_name],
        )

    min_rate = np.nanmin(panel[["sep_longrun_median", "market_median"]].to_numpy())
    max_rate = np.nanmax(panel[["sep_longrun_median", "market_median"]].to_numpy())
    rate_pad = 0.2
    ax_left.plot(
        [min_rate - rate_pad, max_rate + rate_pad],
        [min_rate - rate_pad, max_rate + rate_pad],
        color="#444444",
        linestyle="--",
        linewidth=1.2,
        label="1:1 Anchoring Line",
    )
    ax_left.set_xlim(min_rate - rate_pad, max_rate + rate_pad)
    ax_left.set_ylim(min_rate - rate_pad, max_rate + rate_pad)
    ax_left.set_xlabel("Latest SEP Longer-Run Median Before Survey Due Date (%)", fontweight="bold")
    ax_left.set_ylabel("NY Fed Survey Median (%)", fontweight="bold")
    ax_left.set_title("Survey Medians vs Prior SEP", fontweight="bold")

    ax_right.axhspan(-25, 25, color="#607d8b", alpha=0.08, label="+/-25 bps")
    ax_right.axhline(0, color="#333333", linewidth=1.0)
    ax_right.axvline(0, color="#333333", linewidth=1.0)
    intercept, slope = fit_line(panel)
    if pd.notna(intercept) and pd.notna(slope):
        x_values = np.linspace(
            panel["target_minus_sep_bps"].min(),
            panel["target_minus_sep_bps"].max(),
            100,
        )
        ax_right.plot(
            x_values,
            intercept + slope * x_values,
            color="#333333",
            linewidth=1.8,
            linestyle="--",
            label=f"Pooled fit: {slope:.2f}x",
        )
    ax_right.set_xlabel("Fed Funds Target Midpoint - Prior SEP Median (bps)", fontweight="bold")
    ax_right.set_ylabel("Survey Median - Prior SEP Median (bps)", fontweight="bold")
    ax_right.set_title("Does Current Policy Pull Expectations?", fontweight="bold")

    handles, labels = ax_left.get_legend_handles_labels()
    ax_left.legend(handles, labels, loc="upper left", framealpha=0.95, fontsize=9)
    ax_right.legend(loc="upper left", framealpha=0.95, fontsize=9)

    fig.suptitle(
        "NY Fed Longer-Run Rate Medians vs Real-Time SEP and Policy Rate",
        fontsize=16,
        fontweight="bold",
        y=0.97,
    )
    add_chart_footer(
        fig,
        "Sources: NY Fed Survey of Primary Dealers and Survey of Market Participants; "
        "FRED; FOMC Summary of Economic Projections; author's calculations. "
        "SEP matched strictly before each survey received-by date.",
    )

    plt.tight_layout(rect=(0, 0.065, 1, 0.94))
    plt.savefig(output_path, dpi=150, facecolor="white", bbox_inches="tight")
    plt.close()


def main():
    parser = argparse.ArgumentParser(
        description="Analyze NY Fed survey anchoring to prior SEP and prevailing fed funds target midpoint."
    )
    parser.add_argument(
        "--nyfed-csv",
        default="data_out/nyfed_ff_longrun_percentiles.csv",
        type=Path,
        help="NY Fed survey percentile CSV.",
    )
    parser.add_argument(
        "--sep-csv",
        default="data_out/fred_fed_funds_central_tendency.csv",
        type=Path,
        help="FRED SEP longer-run fed funds CSV.",
    )
    parser.add_argument(
        "--target-csv",
        default="data_out/fed_target_midpoint_vs_neutral.csv",
        type=Path,
        help="FRED target midpoint CSV.",
    )
    parser.add_argument(
        "--output-csv",
        default="data_out/nyfed_sep_anchor_analysis.csv",
        type=Path,
        help="Aligned survey/SEP/target output CSV.",
    )
    parser.add_argument(
        "--summary-csv",
        default="data_out/nyfed_sep_anchor_summary.csv",
        type=Path,
        help="Anchoring summary output CSV.",
    )
    parser.add_argument(
        "--regression-csv",
        default="data_out/nyfed_sep_anchor_regressions.csv",
        type=Path,
        help="OLS regression output CSV.",
    )
    parser.add_argument(
        "--output-png",
        default="data_out/nyfed_sep_anchor_analysis.png",
        type=Path,
        help="Diagnostic chart output PNG.",
    )
    parser.add_argument(
        "--allow-same-day-sep",
        action="store_true",
        help="Allow a SEP released on the received-by date to be matched to that survey.",
    )
    args = parser.parse_args()

    market, sep, target = read_inputs(args.nyfed_csv, args.sep_csv, args.target_csv)
    panel = build_anchor_panel(
        market,
        sep,
        target,
        allow_same_day_sep=args.allow_same_day_sep,
    )
    summary = build_summary(panel)
    regressions = build_regressions(panel)

    args.output_csv.parent.mkdir(parents=True, exist_ok=True)
    panel.to_csv(args.output_csv, index=False)
    summary.to_csv(args.summary_csv, index=False)
    regressions.to_csv(args.regression_csv, index=False)
    plot_anchor_analysis(panel, args.output_png)

    all_summary = summary[summary["sample"] == "All"].iloc[0]
    print(f"Saved {len(panel)} aligned observations to {args.output_csv}")
    print(f"Saved summary to {args.summary_csv}")
    print(f"Saved regressions to {args.regression_csv}")
    print(f"Chart saved to {args.output_png}")
    print(
        "Anchoring summary: "
        f"median abs gap={all_summary['median_abs_gap_bps']:.1f} bps, "
        f"within 25 bps={all_summary['within_25bp_share']:.1%}, "
        f"corr market/SEP={all_summary['corr_market_sep']:.3f}"
    )


if __name__ == "__main__":
    main()
