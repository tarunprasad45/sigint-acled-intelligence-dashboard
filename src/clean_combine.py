#!/usr/bin/env python3
"""
SIGINT — ACLED Data Cleaning & Combination Pipeline
====================================================
Ingests 6 regional ACLED xlsx files, applies documented cleaning steps,
derives analytical columns, and outputs a single master CSV ready for
Power BI or any downstream analysis tool.

Source: ACLED (Armed Conflict Location & Event Data Project)
        https://acleddata.com
Data as of: week of 2026-04-25

Usage
-----
    python clean_combine.py                          # default paths
    python clean_combine.py --data-dir /path/to/raw  # custom input dir
    python clean_combine.py --output /path/to/out.csv

Output
------
    data/processed/acled_master.csv

Columns added by this script
-----------------------------
    SOURCE_FILE         original filename (traceability)
    YEAR                integer year extracted from WEEK
    MONTH               integer month extracted from WEEK
    QUARTER             Q1–Q4 label
    WEEK_STR            ISO week string YYYY-WXX for Power BI time axis
    SEVERITY_SCORE      composite risk score (see formula below)
    SEVERITY_BAND       Low / Medium / High / Critical
    GEOCODE_STATUS      Complete / Missing coords
    POP_EXPOSURE_FILLED 0-filled population exposure (documented imputation)
    DISORDER_PRIMARY    first disorder type when semicolon-delimited
"""

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd
import numpy as np

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

RAW_FILES = {
    "Africa":               "Africa_aggregated_data_up_to_week_of-2026-04-25.xlsx",
    "Asia-Pacific":         "Asia-Pacific_aggregated_data_up_to_week_of-2026-04-25.xlsx",
    "Europe-Central-Asia":  "Europe-Central-Asia_aggregated_data_up_to_week_of-2026-04-25.xlsx",
    "Latin-America":        "Latin-America-the-Caribbean_aggregated_data_up_to_week_of-2026-04-25.xlsx",
    "Middle-East":          "Middle-East_aggregated_data_up_to_week_of-2026-04-25.xlsx",
    "US-Canada":            "US-and-Canada_aggregated_data_up_to_week_of-2026-04-25.xlsx",
}

EXPECTED_COLUMNS = {
    "WEEK", "REGION", "COUNTRY", "ADMIN1",
    "EVENT_TYPE", "SUB_EVENT_TYPE", "EVENTS", "FATALITIES",
    "POPULATION_EXPOSURE", "DISORDER_TYPE", "ID",
    "CENTROID_LATITUDE", "CENTROID_LONGITUDE",
}

SEVERITY_WEIGHTS = {
    "fatalities":           0.50,
    "events":               0.25,
    "population_exposure":  0.25,
}


# ─────────────────────────────────────────────
# Step 1: Ingest
# ─────────────────────────────────────────────

def ingest(data_dir: Path) -> pd.DataFrame:
    frames = []
    for label, filename in RAW_FILES.items():
        path = data_dir / filename
        if not path.exists():
            log.warning("File not found, skipping: %s", path)
            continue

        log.info("Reading %-20s  (%s)", label, filename)
        df = pd.read_excel(path, engine="openpyxl")

        missing = EXPECTED_COLUMNS - set(df.columns)
        if missing:
            log.error("Missing expected columns in %s: %s", filename, missing)
            sys.exit(1)

        df["SOURCE_FILE"] = filename
        log.info("  → %d rows", len(df))
        frames.append(df)

    combined = pd.concat(frames, ignore_index=True)
    log.info("Combined: %d rows across %d files", len(combined), len(frames))
    return combined


# ─────────────────────────────────────────────
# Step 2: Clean
# ─────────────────────────────────────────────

def clean(df: pd.DataFrame) -> pd.DataFrame:
    original_len = len(df)

    # 2a. Parse WEEK as datetime
    df["WEEK"] = pd.to_datetime(df["WEEK"], errors="coerce")
    bad_dates = df["WEEK"].isna().sum()
    if bad_dates:
        log.warning("  %d rows have unparseable WEEK dates — dropping", bad_dates)
        df = df.dropna(subset=["WEEK"])

    # 2b. Strip whitespace from all string columns
    str_cols = df.select_dtypes(include=["object", "str"]).columns.tolist()
    for col in set(str_cols):
        if col in df.columns:
            df[col] = df[col].str.strip()

    # 2c. Normalise DISORDER_TYPE — some rows are semicolon-delimited
    #     e.g. "Political violence; Demonstrations"
    #     Keep original, add DISORDER_PRIMARY for cleaner filtering
    df["DISORDER_PRIMARY"] = (
        df["DISORDER_TYPE"]
        .fillna("Unknown")
        .str.split(";")
        .str[0]
        .str.strip()
    )

    # 2d. ADMIN1 nulls → "National level"
    #     (8 nulls in Europe-Central-Asia — genuinely national-level events)
    null_admin = df["ADMIN1"].isna().sum()
    if null_admin:
        log.info("  ADMIN1: filling %d nulls with 'National level'", null_admin)
    df["ADMIN1"] = df["ADMIN1"].fillna("National level")

    # 2e. POPULATION_EXPOSURE nulls → 0 with documented flag
    #     Nulls occur when ACLED has no population grid data for that location.
    #     Imputation: 0 (conservative — not inflating exposure figures).
    #     See ACLED methodology: https://acleddata.com/acleddatanerd/acled-methodology-and-coding-framework/
    null_pop = df["POPULATION_EXPOSURE"].isna().sum()
    pct_null = null_pop / len(df) * 100
    log.info(
        "  POPULATION_EXPOSURE: %d nulls (%.1f%%) → filled with 0",
        null_pop, pct_null,
    )
    df["POP_EXPOSURE_FILLED"] = df["POPULATION_EXPOSURE"].fillna(0).astype(int)

    # 2f. Geocode status flag
    missing_coords = df["CENTROID_LATITUDE"].isna() | df["CENTROID_LONGITUDE"].isna()
    df["GEOCODE_STATUS"] = np.where(missing_coords, "Missing coords", "Complete")
    if missing_coords.sum():
        log.warning("  %d rows missing geocoordinates", missing_coords.sum())

    # 2g. Drop rows where both EVENTS and FATALITIES are 0 — these are
    #     ACLED 'no event' placeholders that add noise to aggregations
    zero_mask = (df["EVENTS"] == 0) & (df["FATALITIES"] == 0)
    zero_count = zero_mask.sum()
    if zero_count:
        log.info("  Dropping %d zero-event zero-fatality rows", zero_count)
        df = df[~zero_mask]

    # 2h. Ensure numeric columns are correct dtype
    for col in ["EVENTS", "FATALITIES", "ID"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)

    log.info(
        "  Cleaning complete: %d → %d rows (removed %d)",
        original_len, len(df), original_len - len(df),
    )
    return df


# ─────────────────────────────────────────────
# Step 3: Derive analytical columns
# ─────────────────────────────────────────────

def derive(df: pd.DataFrame) -> pd.DataFrame:

    # 3a. Time dimensions
    df["YEAR"]     = df["WEEK"].dt.year
    df["MONTH"]    = df["WEEK"].dt.month
    df["QUARTER"]  = "Q" + df["WEEK"].dt.quarter.astype(str)
    df["WEEK_STR"] = df["WEEK"].dt.strftime("%Y-W%W")

    # 3b. Severity score
    #     Formula: (fatalities × 0.50) + (events × 0.25) + (pop_exposure_norm × 0.25)
    #     Population exposure is normalised to [0, 1] across the full dataset
    #     before weighting so it doesn't dominate the score.
    #
    #     Result is then scaled to [0, 10] for readability.
    #
    pop_max = df["POP_EXPOSURE_FILLED"].max()
    pop_norm = df["POP_EXPOSURE_FILLED"] / pop_max if pop_max > 0 else 0

    fat_max = df["FATALITIES"].max()
    fat_norm = df["FATALITIES"] / fat_max if fat_max > 0 else 0

    evt_max = df["EVENTS"].max()
    evt_norm = df["EVENTS"] / evt_max if evt_max > 0 else 0

    raw_score = (
        fat_norm  * SEVERITY_WEIGHTS["fatalities"] +
        evt_norm  * SEVERITY_WEIGHTS["events"] +
        pop_norm  * SEVERITY_WEIGHTS["population_exposure"]
    )
    df["SEVERITY_SCORE"] = (raw_score * 10).round(2)

    # 3c. Severity band
    df["SEVERITY_BAND"] = pd.cut(
        df["SEVERITY_SCORE"],
        bins=[-0.001, 1, 3, 6, 10],
        labels=["Low", "Medium", "High", "Critical"],
    ).astype(str)

    log.info("  Derived: YEAR, MONTH, QUARTER, WEEK_STR, SEVERITY_SCORE, SEVERITY_BAND")
    return df


# ─────────────────────────────────────────────
# Step 4: Validate
# ─────────────────────────────────────────────

def validate(df: pd.DataFrame) -> None:
    errors = []

    if df["EVENTS"].lt(0).any():
        errors.append("Negative EVENTS values found")
    if df["FATALITIES"].lt(0).any():
        errors.append("Negative FATALITIES values found")
    if df["SEVERITY_SCORE"].gt(10).any() or df["SEVERITY_SCORE"].lt(0).any():
        errors.append("SEVERITY_SCORE outside [0,10]")
    if df["WEEK"].isna().any():
        errors.append("Null WEEK values remain after cleaning")
    if df.duplicated(subset=["WEEK", "COUNTRY", "ADMIN1", "EVENT_TYPE", "SUB_EVENT_TYPE"]).any():
        n = df.duplicated(subset=["WEEK", "COUNTRY", "ADMIN1", "EVENT_TYPE", "SUB_EVENT_TYPE"]).sum()
        errors.append(f"{n} potential duplicate rows (same week/country/admin1/event_type/sub_event_type)")

    if errors:
        log.warning("Validation issues found:")
        for e in errors:
            log.warning("  ⚠  %s", e)
    else:
        log.info("  Validation passed — no issues found")


# ─────────────────────────────────────────────
# Step 5: Export
# ─────────────────────────────────────────────

def export(df: pd.DataFrame, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    final_cols = [
        "SOURCE_FILE",
        "WEEK", "WEEK_STR", "YEAR", "MONTH", "QUARTER",
        "REGION", "COUNTRY", "ADMIN1",
        "EVENT_TYPE", "SUB_EVENT_TYPE",
        "DISORDER_TYPE", "DISORDER_PRIMARY",
        "EVENTS", "FATALITIES",
        "POPULATION_EXPOSURE", "POP_EXPOSURE_FILLED",
        "GEOCODE_STATUS",
        "CENTROID_LATITUDE", "CENTROID_LONGITUDE",
        "SEVERITY_SCORE", "SEVERITY_BAND",
        "ID",
    ]
    df = df[final_cols]

    df.to_csv(output_path, index=False, encoding="utf-8-sig")
    size_mb = output_path.stat().st_size / 1_048_576
    log.info("Exported: %s  (%.1f MB, %d rows, %d columns)",
             output_path, size_mb, len(df), len(df.columns))


# ─────────────────────────────────────────────
# Step 6: Summary report
# ─────────────────────────────────────────────

def summary(df: pd.DataFrame) -> None:
    sep = "─" * 55
    print(f"\n{sep}")
    print("  SIGINT — Pipeline Summary")
    print(sep)
    print(f"  Total rows          : {len(df):>12,}")
    print(f"  Countries           : {df['COUNTRY'].nunique():>12,}")
    print(f"  Date range          : {df['WEEK'].min().date()} → {df['WEEK'].max().date()}")
    print(f"  Total events        : {df['EVENTS'].sum():>12,}")
    print(f"  Total fatalities    : {df['FATALITIES'].sum():>12,}")
    print(f"  Geocode complete    : {(df['GEOCODE_STATUS']=='Complete').sum():>12,}")
    print(f"  Geocode missing     : {(df['GEOCODE_STATUS']=='Missing coords').sum():>12,}")
    print(f"\n  Severity distribution:")
    for band in ["Critical", "High", "Medium", "Low"]:
        n = (df["SEVERITY_BAND"] == band).sum()
        pct = n / len(df) * 100
        print(f"    {band:<10} {n:>8,}  ({pct:.1f}%)")
    print(f"\n  Events by disorder type:")
    for dtype, grp in df.groupby("DISORDER_PRIMARY")["EVENTS"].sum().sort_values(ascending=False).items():
        print(f"    {dtype:<35} {grp:>10,}")
    print(f"\n  Top 5 countries by fatalities:")
    top5 = df.groupby("COUNTRY")["FATALITIES"].sum().sort_values(ascending=False).head(5)
    for country, fat in top5.items():
        print(f"    {country:<30} {fat:>10,}")
    print(sep + "\n")


# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="ACLED multi-region ETL pipeline — clean, combine, and enrich"
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("data/raw"),
        help="Directory containing the 6 raw xlsx files (default: data/raw)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/processed/acled_master.csv"),
        help="Output CSV path (default: data/processed/acled_master.csv)",
    )
    args = parser.parse_args()

    log.info("═" * 55)
    log.info("SIGINT — ACLED ETL Pipeline")
    log.info("═" * 55)

    log.info("Step 1/5  Ingesting raw files from %s", args.data_dir)
    df = ingest(args.data_dir)

    log.info("Step 2/5  Cleaning")
    df = clean(df)

    log.info("Step 3/5  Deriving analytical columns")
    df = derive(df)

    log.info("Step 4/5  Validating")
    validate(df)

    log.info("Step 5/5  Exporting to %s", args.output)
    export(df, args.output)

    summary(df)


if __name__ == "__main__":
    main()
