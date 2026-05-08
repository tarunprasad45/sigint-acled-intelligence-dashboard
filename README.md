# SIGINT — Global Security Events Intelligence Dashboard

> An end-to-end open-source intelligence pipeline: Python ETL across 6 regional ACLED datasets → master dataset → Power BI dashboard tracking political violence, terrorism, and instability across 238 countries.

![Python](https://img.shields.io/badge/Python-3.10%2B-blue?style=flat-square)
![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)
![Data](https://img.shields.io/badge/Source-ACLED-orange?style=flat-square)
![Rows](https://img.shields.io/badge/Rows-946%2C231-informational?style=flat-square)
![Countries](https://img.shields.io/badge/Countries-238-informational?style=flat-square)

---

## What is SIGINT?

SIGINT is a structured OSINT intelligence pipeline that:

1. **Ingests** 6 regional ACLED xlsx exports (Africa, Asia-Pacific, Europe & Central Asia, Latin America, Middle East, US & Canada)
2. **Cleans and combines** them into a single 946,000-row master dataset using a documented Python ETL script
3. **Derives** analytical columns — severity scoring, time dimensions, disorder classification
4. **Visualises** the result in a 5-page Power BI dashboard covering global security events from 1997 to April 2026

The project directly mirrors the workflow of a security intelligence analyst: systematic OSINT collection, structured classification, quality auditing, and visual intelligence reporting.

---

## Data source

**ACLED — Armed Conflict Location & Event Data Project**
[acleddata.com](https://acleddata.com)

ACLED is a disaggregated data collection, analysis, and crisis mapping project that collects real-time data on the locations, dates, actors, fatalities, and types of all reported political violence and protest events worldwide. It is free for researchers.

| File | Region | Rows |
|------|--------|------|
| `Africa_aggregated_data_up_to_week_of-2026-04-25.xlsx` | Africa | 271,370 |
| `Asia-Pacific_aggregated_data_up_to_week_of-2026-04-25.xlsx` | Asia-Pacific | 210,040 |
| `Europe-Central-Asia_aggregated_data_up_to_week_of-2026-04-25.xlsx` | Europe & Central Asia | 120,245 |
| `Latin-America-the-Caribbean_aggregated_data_up_to_week_of-2026-04-25.xlsx` | Latin America | 174,556 |
| `Middle-East_aggregated_data_up_to_week_of-2026-04-25.xlsx` | Middle East | 147,304 |
| `US-and-Canada_aggregated_data_up_to_week_of-2026-04-25.xlsx` | US & Canada | 22,716 |

---

## Pipeline overview

```
data/raw/          data/processed/        Power BI
   6 xlsx    →    acled_master.csv   →   Dashboard
  (946k rows)     (23 columns)         (5 pages)
        ↑
  clean_combine.py
  (Python ETL)
```

---

## Quick start

```bash
git clone https://github.com/yourusername/sigint.git
cd sigint
pip install -r requirements.txt

# Run the ETL pipeline
python clean_combine.py

# Output: data/processed/acled_master.csv
```

**Then in Power BI Desktop:**
1. Get Data → Text/CSV → `data/processed/acled_master.csv`
2. Follow `docs/DASHBOARD_BUILD_GUIDE.md`

---

## ETL pipeline — what `clean_combine.py` does

The script runs 5 documented steps:

| Step | Action | Detail |
|------|--------|--------|
| 1 Ingest | Read all 6 xlsx files | Schema validation — fails loudly if columns are missing |
| 2 Clean | Fix nulls, types, whitespace | ADMIN1 nulls → "National level"; POP_EXPOSURE nulls → 0 (documented) |
| 3 Derive | Add analytical columns | YEAR, MONTH, QUARTER, SEVERITY_SCORE, SEVERITY_BAND, GEOCODE_STATUS |
| 4 Validate | Quality checks | Negative values, out-of-range scores, duplicate detection |
| 5 Export | Write master CSV | Column-ordered, UTF-8-BOM encoded for Power BI compatibility |

Every cleaning decision is documented in the script with the reasoning — not just what was done but why.

```bash
# Custom paths
python clean_combine.py --data-dir /path/to/raw --output /path/to/output.csv
```

---

## Derived columns

| Column | Description | Formula |
|--------|-------------|---------|
| `YEAR` | Calendar year | `WEEK.dt.year` |
| `MONTH` | Calendar month | `WEEK.dt.month` |
| `QUARTER` | Q1–Q4 | `WEEK.dt.quarter` |
| `WEEK_STR` | ISO week label | `YYYY-WXX` |
| `SEVERITY_SCORE` | Composite risk [0–10] | `(fatalities×0.5 + events×0.25 + pop_exposure×0.25)` normalised |
| `SEVERITY_BAND` | Risk tier | Low / Medium / High / Critical |
| `DISORDER_PRIMARY` | First disorder type | Splits semicolon-delimited `DISORDER_TYPE` |
| `GEOCODE_STATUS` | Coordinate completeness | Complete / Missing coords |
| `POP_EXPOSURE_FILLED` | Imputed population exposure | Null → 0 (conservative) |
| `SOURCE_FILE` | Traceability | Original filename |

---

## Dashboard pages

| Page | Focus | Key visuals |
|------|-------|-------------|
| 1 — Global overview | Top-level KPIs and world map | KPI cards, bubble map, trend line, top countries |
| 2 — Regional deep-dive | Region-by-region breakdown | Area chart, YoY bar, fatality heatmap, scatter |
| 3 — Classification & quality audit | Data integrity and source traceability | Geocode completeness, source file audit, classification table |
| 4 — Risk intelligence matrix | Severity scoring and escalation | Risk quadrant, escalation table, quarterly heatmap |
| 5 — Political violence focus | Terrorism and armed conflict | Attack type breakdown, high-fatality events table |

Full build instructions including all DAX measures: `docs/DASHBOARD_BUILD_GUIDE.md`

---

## Dataset statistics (post-cleaning)

| Metric | Value |
|--------|-------|
| Total rows | 946,231 |
| Countries | 238 |
| Date range | 1996-12-28 → 2026-04-25 |
| Total events | 3,019,938 |
| Total fatalities | 2,561,237 |
| Top country (fatalities) | Ukraine — 256,769 |

---

## Project structure

```
sigint/
├── clean_combine.py              ← ETL pipeline (run this first)
├── requirements.txt
├── LICENSE
├── README.md
├── data/
│   ├── raw/                      ← 6 original ACLED xlsx files
│   └── processed/                ← acled_master.csv (gitignored — regenerate)
└── docs/
    ├── DASHBOARD_BUILD_GUIDE.md  ← Full Power BI build instructions + DAX
    └── screenshots/              ← Dashboard page screenshots
```

---

## Disclaimer

All data is sourced from ACLED, a publicly available research dataset. This project is for educational and portfolio purposes. ACLED data is subject to their own terms of use — see [acleddata.com/terms-of-use](https://acleddata.com/terms-of-use/).

---

## License

MIT — see [LICENSE](LICENSE)
