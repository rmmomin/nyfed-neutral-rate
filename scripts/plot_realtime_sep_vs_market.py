#!/usr/bin/env python3
"""
Plot real-time SEP longer-run dots against available NY Fed survey expectations.

For each SEP vintage, market expectations are the latest NY Fed survey
observations whose received-by date is on or before the SEP release date.

Reads:
  - data_out/sep_summary.csv
  - data_out/nyfed_ff_longrun_percentiles.csv

Outputs:
  - data_out/realtime_sep_vs_market.csv
  - data_out/realtime_sep_vs_market.png
"""

from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd


PANEL_ORDER = ["SPD", "SMP", "Combined"]
PANEL_LABELS = {
    "SPD": "Primary Dealers",
    "SMP": "Market Participants",
    "Combined": "Combined Survey",
}
PANEL_COLORS = {
    "SPD": "#1a5f7a",
    "SMP": "#2a9d8f",
    "Combined": "#e63946",
}
PANEL_MARKERS = {
    "SPD": "o",
    "SMP": "v",
    "Combined": "s",
}


def latest_market_by_panel(market: pd.DataFrame, vintage_date: pd.Timestamp) -> pd.DataFrame:
    """Return latest available market survey row for each panel at a vintage."""
    available = market[
        (market["received_by_date"].notna())
        & (market["received_by_date"] <= vintage_date)
        & (market["pctl50"].notna())
    ].copy()
    if available.empty:
        return pd.DataFrame()

    available = available.sort_values(["panel", "received_by_date", "survey_date"])
    latest = available.groupby("panel", as_index=False).tail(1)
    return latest[latest["panel"].isin(PANEL_ORDER)].copy()


def build_realtime_panel(sep: pd.DataFrame, market: pd.DataFrame) -> pd.DataFrame:
    """Build one row per SEP vintage and market panel."""
    rows = []
    for _, sep_row in sep.iterrows():
        vintage_date = sep_row["data_vintage_date"]
        latest = latest_market_by_panel(market, vintage_date)
        for _, market_row in latest.iterrows():
            gap = market_row["pctl50"] - sep_row["p50"]
            rows.append({
                "sep_meeting_date": sep_row["meeting_date"],
                "sep_data_vintage_date": vintage_date,
                "sep_p25": sep_row["p25"],
                "sep_p50": sep_row["p50"],
                "sep_p75": sep_row["p75"],
                "market_panel": market_row["panel"],
                "market_survey_date": market_row["survey_date"],
                "market_received_by_date": market_row["received_by_date"],
                "market_p25": market_row["pctl25"],
                "market_p50": market_row["pctl50"],
                "market_p75": market_row["pctl75"],
                "market_minus_sep_pp": round(gap, 4),
                "market_minus_sep_bps": round(gap * 100, 1),
                "days_between_market_receipt_and_sep": (
                    vintage_date - market_row["received_by_date"]
                ).days,
                "market_source": market_row["source"],
                "market_receipt_source_file": market_row.get("receipt_source_file"),
            })
    return pd.DataFrame(rows)


def plot_realtime_alignment(sep: pd.DataFrame, aligned: pd.DataFrame, output_path: Path) -> None:
    """Plot SEP vs market medians and market-minus-SEP gaps."""
    fig, (ax_top, ax_gap) = plt.subplots(
        2,
        1,
        figsize=(14, 9),
        sharex=True,
        gridspec_kw={"height_ratios": [2.1, 1]},
        facecolor="white",
    )
    for ax in (ax_top, ax_gap):
        ax.set_facecolor("white")
        ax.grid(True, alpha=0.3, linestyle="-", linewidth=0.5)
        ax.set_axisbelow(True)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)

    color_sep = "#263238"

    # SEP IQR and median.
    ax_top.fill_between(
        sep["data_vintage_date"],
        sep["p25"],
        sep["p75"],
        alpha=0.16,
        color=color_sep,
        label="SEP 25th-75th Pctl",
    )
    ax_top.plot(
        sep["data_vintage_date"],
        sep["p50"],
        color=color_sep,
        linewidth=2.6,
        marker="D",
        markersize=4,
        label="SEP Median",
    )

    # Real-time market medians and gaps.
    for panel in PANEL_ORDER:
        panel_df = aligned[aligned["market_panel"] == panel].sort_values("sep_data_vintage_date")
        if panel_df.empty:
            continue
        label = PANEL_LABELS[panel]
        color = PANEL_COLORS[panel]
        marker = PANEL_MARKERS[panel]

        ax_top.plot(
            panel_df["sep_data_vintage_date"],
            panel_df["market_p50"],
            color=color,
            linewidth=1.8,
            marker=marker,
            markersize=5,
            label=f"{label} Median",
        )
        ax_gap.plot(
            panel_df["sep_data_vintage_date"],
            panel_df["market_minus_sep_bps"],
            color=color,
            linewidth=1.7,
            marker=marker,
            markersize=4,
            label=label,
        )

    ax_gap.axhline(0, color="#333333", linewidth=1.0)
    ax_gap.axhspan(-25, 25, color="#607d8b", alpha=0.08, label="+/-25 bps")

    ax_top.set_ylabel("Longer-Run Fed Funds Rate (%)", fontsize=11, fontweight="bold")
    ax_gap.set_ylabel("Market - SEP\n(bps)", fontsize=11, fontweight="bold")
    ax_gap.set_xlabel("SEP Vintage Date", fontsize=11, fontweight="bold")

    ax_top.set_title(
        "Real-Time SEP vs Market Longer-Run Rate Expectations",
        fontsize=15,
        fontweight="bold",
        pad=12,
    )
    ax_top.text(
        0.01,
        0.02,
        "Market series use latest NY Fed survey available by received-by date at each SEP release.",
        transform=ax_top.transAxes,
        fontsize=9,
        color="#666666",
        style="italic",
    )

    all_rates = list(sep["p25"].dropna()) + list(sep["p75"].dropna()) + list(aligned["market_p50"].dropna())
    if all_rates:
        ax_top.set_ylim(max(0, min(all_rates) - 0.25), max(all_rates) + 0.25)

    max_gap = aligned["market_minus_sep_bps"].abs().max()
    if pd.notna(max_gap):
        limit = max(50, ((max_gap // 25) + 1) * 25)
        ax_gap.set_ylim(-limit, limit)

    ax_gap.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax_gap.xaxis.set_major_locator(mdates.YearLocator())
    plt.setp(ax_gap.get_xticklabels(), rotation=45, ha="right")

    ax_top.legend(loc="upper left", framealpha=0.95, fontsize=9, ncol=2)
    ax_gap.legend(loc="upper left", framealpha=0.95, fontsize=9, ncol=4)

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, facecolor="white", bbox_inches="tight")
    plt.close()


def main():
    sep_path = Path("data_out/sep_summary.csv")
    market_path = Path("data_out/nyfed_ff_longrun_percentiles.csv")
    output_csv = Path("data_out/realtime_sep_vs_market.csv")
    output_png = Path("data_out/realtime_sep_vs_market.png")

    sep = pd.read_csv(sep_path, parse_dates=["meeting_date", "data_vintage_date"])
    sep = sep[sep["horizon"].str.lower().str.contains("longer", na=False)].copy()
    sep = sep.sort_values("data_vintage_date")

    market = pd.read_csv(
        market_path,
        parse_dates=["survey_date", "received_by_date"],
    )
    market = market[market["pctl50"].notna()].copy()

    aligned = build_realtime_panel(sep, market)
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    aligned.to_csv(output_csv, index=False)

    plot_realtime_alignment(sep, aligned, output_png)

    print(f"Saved {len(aligned)} aligned rows to {output_csv}")
    print(f"Chart saved to {output_png}")
    if not aligned.empty:
        print(
            "Median absolute market-SEP gap by panel (bps):\n"
            + aligned.groupby("market_panel")["market_minus_sep_bps"].apply(lambda s: s.abs().median()).to_string()
        )


if __name__ == "__main__":
    main()
