"""Plot longer-run federal funds rate percentiles over time."""

import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from pathlib import Path

# Load data
csv_path = Path("data_out/nyfed_ff_longrun_percentiles.csv")
df = pd.read_csv(csv_path, parse_dates=["survey_date"])

# Filter to Combined panel (or use all if you prefer)
df_combined = df[df["panel"] == "Combined"].sort_values("survey_date")

# Set up the plot with a clean, modern style
plt.style.use("seaborn-v0_8-whitegrid")
fig, ax = plt.subplots(figsize=(12, 6))

# Plot percentiles
ax.plot(df_combined["survey_date"], df_combined["pctl50"], 
        color="#1f77b4", linewidth=2.5, label="Median (50th)", linestyle="-")
ax.plot(df_combined["survey_date"], df_combined["pctl25"], 
        color="#2ca02c", linewidth=1.5, label="25th Percentile", linestyle=":")
ax.plot(df_combined["survey_date"], df_combined["pctl75"], 
        color="#d62728", linewidth=1.5, label="75th Percentile", linestyle=":")

# Fill between 25th and 75th percentiles
ax.fill_between(df_combined["survey_date"], 
                df_combined["pctl25"], df_combined["pctl75"],
                alpha=0.15, color="#1f77b4")

# Formatting
ax.set_xlabel("Survey Date", fontsize=12)
ax.set_ylabel("Rate (%)", fontsize=12)
ax.set_title("NY Fed Survey: Longer-Run Federal Funds Rate Expectations", 
             fontsize=14, fontweight="bold")

# Format x-axis dates
ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
ax.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
plt.xticks(rotation=45, ha="right")

# Legend
ax.legend(loc="upper right", frameon=True, fontsize=10)

# Grid styling
ax.grid(True, alpha=0.3)
ax.set_axisbelow(True)

# Tight layout
plt.tight_layout()

# Save and show
output_path = Path("data_out/longrun_rates_plot.png")
plt.savefig(output_path, dpi=150, bbox_inches="tight", facecolor="white")
print(f"Plot saved to: {output_path}")

plt.show()

