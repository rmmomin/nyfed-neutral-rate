#!/usr/bin/env python3
"""
Analyze whether SEP median changes predict later NY Fed survey median changes.

For each NY Fed survey observation, the predictor is the latest SEP median change
released strictly before the survey received-by date. The event-level panel keeps
the first survey received after each SEP release for each panel.

Reads:
  - data_out/nyfed_ff_longrun_percentiles.csv
  - data_out/fred_fed_funds_central_tendency.csv

Outputs:
  - data_out/sep_future_nyfed_predictive_analysis.csv
  - data_out/sep_future_nyfed_predictive_event_analysis.csv
  - data_out/sep_future_nyfed_predictive_summary.csv
  - data_out/sep_future_nyfed_predictive_regressions.csv
  - data_out/sep_future_nyfed_predictive.png
"""

import argparse
import sys
from pathlib import Path
from typing import Dict, List, Tuple

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


def read_inputs(nyfed_path: Path, sep_path: Path) -> Tuple[pd.DataFrame, pd.DataFrame]:
    market = pd.read_csv(
        nyfed_path,
        parse_dates=["survey_date", "distributed_date", "received_by_date"],
    )
    sep = pd.read_csv(sep_path, parse_dates=["date"])
    sep = sep[["date", "longrun_median"]].dropna().rename(
        columns={"date": "sep_date", "longrun_median": "sep_median"}
    )
    sep = sep.sort_values("sep_date")
    sep["previous_sep_date"] = sep["sep_date"].shift(1)
    sep["previous_sep_median"] = sep["sep_median"].shift(1)
    sep["sep_change_pp"] = sep["sep_median"] - sep["previous_sep_median"]
    sep["sep_change_bps"] = (sep["sep_change_pp"] * 100).round(1)
    return market, sep.dropna(subset=["sep_change_bps"]).copy()


def prepare_market(market: pd.DataFrame) -> pd.DataFrame:
    rows = market[
        market["panel"].isin(PANEL_ORDER)
        & market["pctl50"].notna()
        & market["received_by_date"].notna()
    ].copy()
    rows = rows.sort_values(["panel", "received_by_date", "survey_date"])
    rows["previous_survey_date"] = rows.groupby("panel")["survey_date"].shift(1)
    rows["previous_received_by_date"] = rows.groupby("panel")["received_by_date"].shift(1)
    rows["previous_market_median"] = rows.groupby("panel")["pctl50"].shift(1)
    rows["survey_change_pp"] = rows["pctl50"] - rows["previous_market_median"]
    rows["survey_change_bps"] = (rows["survey_change_pp"] * 100).round(1)
    return rows


def build_survey_level_panel(market: pd.DataFrame, sep: pd.DataFrame) -> pd.DataFrame:
    aligned = pd.merge_asof(
        market.sort_values("received_by_date"),
        sep.sort_values("sep_date"),
        left_on="received_by_date",
        right_on="sep_date",
        direction="backward",
        allow_exact_matches=False,
    )
    aligned = aligned.dropna(subset=["survey_change_bps", "sep_change_bps"]).copy()
    aligned["days_since_sep_release"] = (
        aligned["received_by_date"] - aligned["sep_date"]
    ).dt.days

    output_columns = [
        "survey_date",
        "received_by_date",
        "panel",
        "pctl50",
        "previous_survey_date",
        "previous_received_by_date",
        "previous_market_median",
        "survey_change_pp",
        "survey_change_bps",
        "sep_date",
        "sep_median",
        "previous_sep_date",
        "previous_sep_median",
        "sep_change_pp",
        "sep_change_bps",
        "days_since_sep_release",
        "source",
        "local_path",
        "receipt_source_file",
    ]
    return aligned[output_columns].sort_values(["received_by_date", "panel"])


def build_event_level_panel(market: pd.DataFrame, sep: pd.DataFrame) -> pd.DataFrame:
    """Use the first survey received after each SEP release for each panel."""
    rows: List[Dict] = []
    market = market.dropna(subset=["survey_change_bps"]).copy()
    sep = sep.reset_index(drop=True)

    for idx, sep_row in sep.iterrows():
        sep_date = sep_row["sep_date"]
        next_sep_date = sep.loc[idx + 1, "sep_date"] if idx + 1 < len(sep) else pd.Timestamp.max
        available = market[
            (market["received_by_date"] > sep_date)
            & (market["received_by_date"] < next_sep_date)
        ].copy()
        if available.empty:
            continue

        for panel, group in available.groupby("panel"):
            first = group.sort_values(["received_by_date", "survey_date"]).iloc[0]
            rows.append({
                "sep_date": sep_date,
                "previous_sep_date": sep_row["previous_sep_date"],
                "panel": panel,
                "sep_median": sep_row["sep_median"],
                "previous_sep_median": sep_row["previous_sep_median"],
                "sep_change_pp": sep_row["sep_change_pp"],
                "sep_change_bps": sep_row["sep_change_bps"],
                "survey_date": first["survey_date"],
                "received_by_date": first["received_by_date"],
                "market_median": first["pctl50"],
                "previous_market_median": first["previous_market_median"],
                "survey_change_pp": first["survey_change_pp"],
                "survey_change_bps": first["survey_change_bps"],
                "days_since_sep_release": (first["received_by_date"] - sep_date).days,
            })

    return pd.DataFrame(rows).sort_values(["sep_date", "panel"])


def directional_stats(group: pd.DataFrame) -> Dict:
    both_nonzero = group[
        (group["sep_change_bps"] != 0)
        & (group["survey_change_bps"] != 0)
    ]
    sep_nonzero = group[group["sep_change_bps"] != 0]
    survey_nonzero = group[group["survey_change_bps"] != 0]

    def sign_match(data: pd.DataFrame) -> float:
        if data.empty:
            return np.nan
        return (
            np.sign(data["sep_change_bps"])
            == np.sign(data["survey_change_bps"])
        ).mean()

    return {
        "both_nonzero_n": len(both_nonzero),
        "directional_accuracy_both_nonzero": sign_match(both_nonzero),
        "sep_nonzero_n": len(sep_nonzero),
        "directional_accuracy_when_sep_moves": sign_match(sep_nonzero),
        "survey_nonzero_n": len(survey_nonzero),
        "directional_accuracy_when_survey_moves": sign_match(survey_nonzero),
    }


def summarize(panel: pd.DataFrame, sample_type: str) -> pd.DataFrame:
    rows: List[Dict] = []
    groups: List[Tuple[str, pd.DataFrame]] = [("All", panel)]
    groups.extend((panel_name, panel[panel["panel"] == panel_name]) for panel_name in PANEL_ORDER)

    for sample, group in groups:
        if group.empty:
            continue
        coefficients, r_squared, _ = ols(
            group["survey_change_bps"],
            group[["sep_change_bps"]],
        )
        stats = directional_stats(group)
        rows.append({
            "sample_type": sample_type,
            "sample": sample,
            "n": len(group),
            "first_received_by_date": group["received_by_date"].min().date(),
            "last_received_by_date": group["received_by_date"].max().date(),
            "corr_sep_change_survey_change": round(
                group[["sep_change_bps", "survey_change_bps"]].corr().iloc[0, 1],
                3,
            ),
            "r_squared": round(r_squared, 3),
            "intercept_bps": round(coefficients.get("intercept", np.nan), 2),
            "slope_survey_bps_per_sep_bp": round(
                coefficients.get("sep_change_bps", np.nan),
                3,
            ),
            "mean_abs_sep_change_bps": round(group["sep_change_bps"].abs().mean(), 1),
            "mean_abs_survey_change_bps": round(group["survey_change_bps"].abs().mean(), 1),
            "median_abs_sep_change_bps": round(group["sep_change_bps"].abs().median(), 1),
            "median_abs_survey_change_bps": round(group["survey_change_bps"].abs().median(), 1),
            **{
                key: round(value, 3) if isinstance(value, float) and pd.notna(value) else value
                for key, value in stats.items()
            },
            "avg_days_since_sep_release": round(group["days_since_sep_release"].mean(), 1),
        })
    return pd.DataFrame(rows)


def build_regressions(
    survey_panel: pd.DataFrame,
    event_panel: pd.DataFrame,
) -> pd.DataFrame:
    rows: List[Dict] = []
    for sample_type, panel in [
        ("survey_level", survey_panel),
        ("event_level_first_survey", event_panel),
    ]:
        groups: List[Tuple[str, pd.DataFrame]] = [("All", panel)]
        groups.extend((panel_name, panel[panel["panel"] == panel_name]) for panel_name in PANEL_ORDER)
        for sample, group in groups:
            if group.empty:
                continue
            coefficients, r_squared, n_obs = ols(
                group["survey_change_bps"],
                group[["sep_change_bps"]],
            )
            rows.append({
                "sample_type": sample_type,
                "sample": sample,
                "model": "survey_change_bps_on_sep_change_bps",
                "n": n_obs,
                "r_squared": round(r_squared, 3),
                "intercept": round(coefficients.get("intercept", np.nan), 4),
                "sep_change_bps": round(coefficients.get("sep_change_bps", np.nan), 4),
            })

        panel_fe = panel.copy()
        for panel_name in ["Combined", "SMP"]:
            panel_fe[f"panel_fe_{panel_name.lower()}"] = (
                panel_fe["panel"] == panel_name
            ).astype(float)
        coefficients, r_squared, n_obs = ols(
            panel_fe["survey_change_bps"],
            panel_fe[["sep_change_bps", "panel_fe_combined", "panel_fe_smp"]],
        )
        rows.append({
            "sample_type": sample_type,
            "sample": "All",
            "model": "survey_change_bps_on_sep_change_bps_panel_fe",
            "n": n_obs,
            "r_squared": round(r_squared, 3),
            "intercept": round(coefficients.get("intercept", np.nan), 4),
            "sep_change_bps": round(coefficients.get("sep_change_bps", np.nan), 4),
            "panel_fe_combined": round(coefficients.get("panel_fe_combined", np.nan), 4),
            "panel_fe_smp": round(coefficients.get("panel_fe_smp", np.nan), 4),
        })

    return pd.DataFrame(rows)


def plot_predictive_analysis(
    survey_panel: pd.DataFrame,
    event_panel: pd.DataFrame,
    output_path: Path,
) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(15, 7), facecolor="white", sharey=True)
    configs = [
        ("All Survey Observations After SEP", survey_panel),
        ("First Survey After Each SEP", event_panel),
    ]

    for ax, (title, panel) in zip(axes, configs):
        ax.set_facecolor("white")
        ax.grid(True, alpha=0.3, linestyle="-", linewidth=0.5)
        ax.set_axisbelow(True)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.axhline(0, color="#333333", linewidth=1.0)
        ax.axvline(0, color="#333333", linewidth=1.0)

        for panel_name in PANEL_ORDER:
            group = panel[panel["panel"] == panel_name]
            if group.empty:
                continue
            ax.scatter(
                group["sep_change_bps"],
                group["survey_change_bps"],
                s=42,
                color=PANEL_COLORS[panel_name],
                marker=PANEL_MARKERS[panel_name],
                edgecolors="white",
                linewidths=0.5,
                alpha=0.85,
                label=PANEL_LABELS[panel_name],
            )

        coefficients, r_squared, _ = ols(
            panel["survey_change_bps"],
            panel[["sep_change_bps"]],
        )
        slope = coefficients.get("sep_change_bps", np.nan)
        intercept = coefficients.get("intercept", np.nan)
        if pd.notna(slope) and pd.notna(intercept):
            x_values = np.linspace(
                panel["sep_change_bps"].min(),
                panel["sep_change_bps"].max(),
                100,
            )
            ax.plot(
                x_values,
                intercept + slope * x_values,
                color="#333333",
                linestyle="--",
                linewidth=1.8,
                label=f"Fit: {slope:.2f}x, R2={r_squared:.2f}",
            )

        ax.set_title(title, fontweight="bold")
        ax.set_xlabel("SEP Median Change (bps)", fontweight="bold")
        ax.legend(loc="upper left", framealpha=0.95, fontsize=9)

    axes[0].set_ylabel("Next NY Fed Survey Median Change (bps)", fontweight="bold")
    fig.suptitle(
        "Do SEP Median Changes Predict Later NY Fed Survey Median Changes?",
        fontsize=16,
        fontweight="bold",
        y=0.97,
    )
    add_chart_footer(
        fig,
        "Sources: FRED; FOMC Summary of Economic Projections; NY Fed Survey of "
        "Primary Dealers and Survey of Market Participants; author's calculations. "
        "Survey-level uses latest SEP released strictly before survey received-by date.",
    )
    plt.tight_layout(rect=(0, 0.065, 1, 0.94))
    plt.savefig(output_path, dpi=150, facecolor="white", bbox_inches="tight")
    plt.close()


def main():
    parser = argparse.ArgumentParser(
        description="Analyze whether SEP median changes predict later NY Fed survey median changes."
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
        "--output-csv",
        default="data_out/sep_future_nyfed_predictive_analysis.csv",
        type=Path,
        help="Survey-level aligned output CSV.",
    )
    parser.add_argument(
        "--event-output-csv",
        default="data_out/sep_future_nyfed_predictive_event_analysis.csv",
        type=Path,
        help="Event-level first-survey-after-SEP output CSV.",
    )
    parser.add_argument(
        "--summary-csv",
        default="data_out/sep_future_nyfed_predictive_summary.csv",
        type=Path,
        help="Predictive summary output CSV.",
    )
    parser.add_argument(
        "--regression-csv",
        default="data_out/sep_future_nyfed_predictive_regressions.csv",
        type=Path,
        help="Regression output CSV.",
    )
    parser.add_argument(
        "--output-png",
        default="data_out/sep_future_nyfed_predictive.png",
        type=Path,
        help="Diagnostic chart output PNG.",
    )
    args = parser.parse_args()

    market_raw, sep = read_inputs(args.nyfed_csv, args.sep_csv)
    market = prepare_market(market_raw)
    survey_panel = build_survey_level_panel(market, sep)
    event_panel = build_event_level_panel(market, sep)
    summary = pd.concat(
        [
            summarize(survey_panel, "survey_level"),
            summarize(event_panel, "event_level_first_survey"),
        ],
        ignore_index=True,
    )
    regressions = build_regressions(survey_panel, event_panel)

    args.output_csv.parent.mkdir(parents=True, exist_ok=True)
    survey_panel.to_csv(args.output_csv, index=False)
    event_panel.to_csv(args.event_output_csv, index=False)
    summary.to_csv(args.summary_csv, index=False)
    regressions.to_csv(args.regression_csv, index=False)
    plot_predictive_analysis(survey_panel, event_panel, args.output_png)

    survey_all = summary[
        (summary["sample_type"] == "survey_level") & (summary["sample"] == "All")
    ].iloc[0]
    event_all = summary[
        (summary["sample_type"] == "event_level_first_survey") & (summary["sample"] == "All")
    ].iloc[0]
    print(f"Saved {len(survey_panel)} survey-level rows to {args.output_csv}")
    print(f"Saved {len(event_panel)} event-level rows to {args.event_output_csv}")
    print(f"Saved summary to {args.summary_csv}")
    print(f"Saved regressions to {args.regression_csv}")
    print(f"Chart saved to {args.output_png}")
    print(
        "Predictive summary: "
        f"survey-level R2={survey_all['r_squared']:.3f}, "
        f"slope={survey_all['slope_survey_bps_per_sep_bp']:.3f}; "
        f"event-level R2={event_all['r_squared']:.3f}, "
        f"slope={event_all['slope_survey_bps_per_sep_bp']:.3f}"
    )


if __name__ == "__main__":
    main()
