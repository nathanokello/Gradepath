"""
Cleans an uploaded CSV/Excel file against the trained model's schema.

Rule: any missing, invalid, out-of-range, or outlier value is treated as
missing and filled with the column's median (numeric) or mode (categorical).
Duplicate rows are dropped entirely, not filled.

Usage:
    from clean_data import clean_dataframe
    cleaned_df, report = clean_dataframe(raw_df)
"""

import pandas as pd
import numpy as np

# Valid ranges/types per feature, based on the training dataset's schema.
# "numeric" = continuous, "binary" = 0/1, "ordinal" = bounded integer scale.
SCHEMA = {
    "StudyTimeWeekly":  {"type": "numeric", "min": 0,  "max": 20},
    "Absences":         {"type": "numeric_int", "min": 0,  "max": 29},
    "Tutoring":         {"type": "binary",  "min": 0,  "max": 1},
    "ParentalSupport":  {"type": "ordinal", "min": 0,  "max": 4},
    "ParentalEducation":{"type": "ordinal", "min": 0,  "max": 4},
    "Extracurricular":  {"type": "binary",  "min": 0,  "max": 1},
    "Sports":           {"type": "binary",  "min": 0,  "max": 1},
    "Music":            {"type": "binary",  "min": 0,  "max": 1},
    "Volunteering":     {"type": "binary",  "min": 0,  "max": 1},
}
REQUIRED_COLUMNS = list(SCHEMA.keys())


def match_schema_columns(df):
    """Case-insensitive, whitespace-trimmed match of uploaded columns to
    the required schema. Renames matched columns to the exact schema name.
    Returns (renamed_df, missing_columns)."""
    normalized = {c.strip().lower(): c for c in df.columns}
    rename_map = {}
    missing = []
    for required in REQUIRED_COLUMNS:
        key = required.strip().lower()
        if key in normalized:
            rename_map[normalized[key]] = required
        else:
            missing.append(required)
    df = df.rename(columns=rename_map)
    return df, missing


def clean_dataframe(df):
    """Returns (cleaned_df, report). Raises ValueError if required columns
    are missing entirely."""
    report = {
        "rows_in": len(df),
        "missing_columns": [],
        "duplicates_removed": 0,
        "values_fixed": {},  # column -> count of missing/invalid/outlier values filled
        "rows_out": None,
    }

    df, missing = match_schema_columns(df)
    if missing:
        report["missing_columns"] = missing
        raise ValueError(
            f"Uploaded file is missing required columns: {missing}"
        )

    df = df.copy()

    # Drop exact duplicate rows (based on the required feature columns)
    before = len(df)
    df = df.drop_duplicates(subset=REQUIRED_COLUMNS)
    report["duplicates_removed"] = before - len(df)

    df = df.reset_index(drop=True)

    for col, rules in SCHEMA.items():
        series = df[col]

        # Step 1: coerce to numeric, forcing unparseable text to NaN
        series = pd.to_numeric(
            series.astype(str).str.strip(), errors="coerce"
        )

        # Step 2: treat out-of-range values as missing too
        out_of_range = (series < rules["min"]) | (series > rules["max"])
        invalid_count = int(series.isna().sum() + out_of_range.sum())
        series[out_of_range] = np.nan

        # Step 3: fill missing/invalid/out-of-range with median or mode
        if rules["type"] in ("numeric", "numeric_int"):
            fill_value = series.median()
        else:  # binary / ordinal -> mode
            mode = series.mode(dropna=True)
            fill_value = mode.iloc[0] if not mode.empty else rules["min"]

        series = series.fillna(fill_value)

        # Binary/ordinal/count columns should end up as clean integers
        if rules["type"] in ("binary", "ordinal", "numeric_int"):
            series = series.round().astype(int)

        df[col] = series
        if invalid_count > 0:
            report["values_fixed"][col] = invalid_count

    report["rows_out"] = len(df)
    return df, report


def print_report(report):
    print(f"Rows in:  {report['rows_in']}")
    print(f"Duplicates removed: {report['duplicates_removed']}")
    if report["values_fixed"]:
        print("Values fixed (missing/invalid/out-of-range -> median/mode):")
        for col, count in report["values_fixed"].items():
            print(f"  {col}: {count}")
    else:
        print("Values fixed: none")
    print(f"Rows out: {report['rows_out']}")
