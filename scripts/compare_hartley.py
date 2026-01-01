#!/usr/bin/env python3
"""
Compare our extracted SPD data with Hartley (2024) US data.

Creates a comparison spreadsheet showing alignment and divergences.
"""

import pandas as pd
from pathlib import Path


def main():
    print("=" * 60)
    print("Comparing SPD data with Hartley (2024)")
    print("=" * 60)
    
    # Load our data - SPD only
    our_data = pd.read_csv("data_out/nyfed_ff_longrun_percentiles.csv", parse_dates=["survey_date"])
    our_spd = our_data[our_data["panel"] == "SPD"].copy()
    our_spd = our_spd.sort_values("survey_date")
    
    print(f"Our SPD data: {len(our_spd)} observations")
    print(f"  Date range: {our_spd['survey_date'].min().strftime('%Y-%m')} to {our_spd['survey_date'].max().strftime('%Y-%m')}")
    
    # Load Hartley data (header at row 2)
    hartley_path = Path("external_data/Hartley2024_RStar_12312025.xlsx")
    hartley_df = pd.read_excel(hartley_path, header=2)
    
    # Skip the first row which has labels
    hartley_df = hartley_df.iloc[1:].copy()
    
    # Extract US data
    date_col = hartley_df.columns[1]  # Unnamed: 1 contains dates
    us_median_col = 'U.S.'
    us_p25_col = hartley_df.columns[3]  # Unnamed: 3
    us_p75_col = hartley_df.columns[4]  # Unnamed: 4
    
    hartley_us = pd.DataFrame({
        'date': pd.to_datetime(hartley_df[date_col]),
        'hartley_median': pd.to_numeric(hartley_df[us_median_col], errors='coerce'),
        'hartley_p25': pd.to_numeric(hartley_df[us_p25_col], errors='coerce'),
        'hartley_p75': pd.to_numeric(hartley_df[us_p75_col], errors='coerce'),
    })
    
    # Drop rows without valid US data
    hartley_us = hartley_us.dropna(subset=['hartley_median'])
    
    # Normalize dates to start of month
    hartley_us['date'] = hartley_us['date'].apply(lambda x: x.replace(day=1))
    
    print(f"\nHartley US data: {len(hartley_us)} observations")
    print(f"  Date range: {hartley_us['date'].min().strftime('%Y-%m')} to {hartley_us['date'].max().strftime('%Y-%m')}")
    
    # Prepare our data for merge
    our_spd['date'] = our_spd['survey_date'].apply(lambda x: x.replace(day=1))
    our_merge = our_spd[['date', 'pctl25', 'pctl50', 'pctl75', 'source']].copy()
    our_merge.columns = ['date', 'our_p25', 'our_median', 'our_p75', 'source']
    
    # Merge
    comparison = pd.merge(hartley_us, our_merge, on='date', how='outer')
    comparison = comparison.sort_values('date')
    
    # Calculate difference
    comparison['median_diff'] = comparison['our_median'] - comparison['hartley_median']
    comparison['abs_diff'] = comparison['median_diff'].abs()
    
    # Summary stats
    matched = comparison[comparison['our_median'].notna() & comparison['hartley_median'].notna()]
    
    print(f"\n" + "=" * 60)
    print("COMPARISON SUMMARY (SPD vs Hartley US)")
    print("=" * 60)
    print(f"Matched observations: {len(matched)}")
    
    if len(matched) > 0:
        print(f"Mean absolute difference: {matched['abs_diff'].mean():.3f}%")
        print(f"Max absolute difference: {matched['abs_diff'].max():.3f}%")
        print(f"Observations with exact match: {(matched['abs_diff'] < 0.01).sum()}")
        print(f"Observations within 0.1%: {(matched['abs_diff'] <= 0.1).sum()}")
        print(f"Observations within 0.25%: {(matched['abs_diff'] <= 0.25).sum()}")
        
        # Show largest divergences
        large_diff = matched[matched['abs_diff'] > 0.1].sort_values('abs_diff', ascending=False)
        if len(large_diff) > 0:
            print(f"\nLargest divergences (>0.1%):")
            for _, row in large_diff.head(10).iterrows():
                print(f"  {row['date'].strftime('%Y-%m')}: Our={row['our_median']:.2f}%, Hartley={row['hartley_median']:.2f}%, Diff={row['median_diff']:+.2f}%")
    
    # Only Hartley
    only_hartley = comparison[comparison['our_median'].isna() & comparison['hartley_median'].notna()]
    if len(only_hartley) > 0:
        print(f"\nDates in Hartley but not in our SPD data: {len(only_hartley)}")
        for _, row in only_hartley.head(5).iterrows():
            print(f"  {row['date'].strftime('%Y-%m')}: Hartley={row['hartley_median']:.2f}%")
    
    # Only ours
    only_ours = comparison[comparison['hartley_median'].isna() & comparison['our_median'].notna()]
    if len(only_ours) > 0:
        print(f"\nDates in our SPD data but not in Hartley: {len(only_ours)}")
        for _, row in only_ours.head(5).iterrows():
            print(f"  {row['date'].strftime('%Y-%m')}: Our={row['our_median']:.2f}%")
    
    # Prepare output
    output_df = comparison.copy()
    output_df['date'] = output_df['date'].dt.strftime('%Y-%m-%d')
    
    # Reorder columns
    output_df = output_df[[
        'date', 
        'our_median', 'our_p25', 'our_p75',
        'hartley_median', 'hartley_p25', 'hartley_p75',
        'median_diff', 'abs_diff',
        'source'
    ]]
    
    # Save comparison
    output_path = Path("data_out/us_rstar_comparison.xlsx")
    output_df.to_excel(output_path, index=False)
    print(f"\nComparison saved to: {output_path}")
    
    print("=" * 60)


if __name__ == "__main__":
    main()
