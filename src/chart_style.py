"""Shared chart styling helpers."""


BRAND_TEXT = "@momin_rayhan"
FOOTER_COLOR = "#555555"
BRAND_COLOR = "#263238"


def add_chart_footer(fig, source_text: str, brand_text: str = BRAND_TEXT) -> None:
    """Add a source footnote and right-aligned personal branding to a figure."""
    fig.text(
        0.01,
        0.015,
        source_text,
        ha="left",
        va="bottom",
        fontsize=8.5,
        color=FOOTER_COLOR,
        style="italic",
    )
    fig.text(
        0.99,
        0.015,
        brand_text,
        ha="right",
        va="bottom",
        fontsize=9,
        color=BRAND_COLOR,
        fontweight="bold",
    )
