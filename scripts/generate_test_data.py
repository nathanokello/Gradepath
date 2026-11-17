"""
Generates synthetic test CSVs matching the exact schema used to train the model.
Produces 4 files:
  - type1_clean.csv    (no GPA/GradeClass, no data issues)
  - type1_unclean.csv  (no GPA/GradeClass, deliberately messy)
  - type2_clean.csv    (has GPA/GradeClass, no data issues)
  - type2_unclean.csv  (has GPA/GradeClass, deliberately messy)

Column names match the training schema exactly, per the plan: random data
uses the training schema as reference for column names, only values vary.
"""

import numpy as np
import pandas as pd

RNG = np.random.default_rng(42)
N_ROWS = 60

FEATURES = [
    "StudyTimeWeekly", "Absences", "Tutoring",
    "ParentalSupport", "ParentalEducation",
    "Extracurricular", "Sports", "Music", "Volunteering",
]
# Non-predictive columns kept for realism / exploratory viz, matching the
# original dataset's schema (not used by the model itself)
EXTRA_COLS = ["Age", "Gender", "Ethnicity"]


def gpa_to_gradeclass(gpa):
    if gpa >= 3.5:
        return 0
    elif gpa >= 3.0:
        return 1
    elif gpa >= 2.5:
        return 2
    elif gpa >= 2.0:
        return 3
    else:
        return 4


def make_base_dataframe(n=N_ROWS):
    absences = RNG.integers(0, 30, n)
    study_time = RNG.uniform(0, 20, n).round(1)
    tutoring = RNG.integers(0, 2, n)
    parental_support = RNG.integers(0, 5, n)
    parental_education = RNG.integers(0, 5, n)
    extracurricular = RNG.integers(0, 2, n)
    sports = RNG.integers(0, 2, n)
    music = RNG.integers(0, 2, n)
    volunteering = RNG.integers(0, 2, n)
    age = RNG.integers(15, 19, n)
    gender = RNG.integers(0, 2, n)
    ethnicity = RNG.integers(0, 4, n)

    # GPA modeled with Absences dominant (matches the real correlation found
    # in EDA: r=-0.92), small contributions from the weak-signal features,
    # plus noise. Clipped to a valid 0-4 range.
    noise = RNG.normal(0, 0.25, n)
    gpa = (
        3.9
        - 0.09 * absences
        + 0.01 * study_time
        + 0.05 * parental_support
        + 0.04 * tutoring
        + noise
    )
    gpa = np.clip(gpa, 0.0, 4.0).round(2)
    grade_class = [gpa_to_gradeclass(g) for g in gpa]

    df = pd.DataFrame({
        "StudyTimeWeekly": study_time,
        "Absences": absences,
        "Tutoring": tutoring,
        "ParentalSupport": parental_support,
        "ParentalEducation": parental_education,
        "Extracurricular": extracurricular,
        "Sports": sports,
        "Music": music,
        "Volunteering": volunteering,
        "Age": age,
        "Gender": gender,
        "Ethnicity": ethnicity,
        "GPA": gpa,
        "GradeClass": grade_class,
    })
    return df


def make_unclean(df):
    """Introduce realistic messiness while keeping column names exact."""
    df = df.copy()
    n = len(df)

    # Missing values scattered across a few columns
    for col in ["StudyTimeWeekly", "ParentalSupport", "Tutoring"]:
        idx = RNG.choice(n, size=max(1, n // 12), replace=False)
        df.loc[idx, col] = np.nan

    # Out-of-range / invalid values
    idx = RNG.choice(n, size=max(1, n // 15), replace=False)
    df.loc[idx, "Absences"] = -5  # negative absences, invalid

    idx = RNG.choice(n, size=max(1, n // 15), replace=False)
    df.loc[idx, "StudyTimeWeekly"] = 999  # unrealistic outlier

    # Wrong dtype: numbers stored as text, with stray whitespace
    df["Absences"] = df["Absences"].astype(object)
    idx = RNG.choice(n, size=max(1, n // 10), replace=False)
    df.loc[idx, "Absences"] = df.loc[idx, "Absences"].astype(str) + " "

    # Duplicate a few rows
    dup_rows = df.sample(n=max(1, n // 20), random_state=1)
    df = pd.concat([df, dup_rows], ignore_index=True)

    # Shuffle row order so duplicates aren't obviously at the end
    df = df.sample(frac=1, random_state=2).reset_index(drop=True)
    return df


def main():
    base = make_base_dataframe()

    # Type 2: has GPA/GradeClass
    type2_clean = base.copy()
    type2_unclean = make_unclean(base)

    # Type 1: no GPA/GradeClass (drop those columns)
    type1_clean = base.drop(columns=["GPA", "GradeClass"]).copy()
    type1_unclean = make_unclean(base).drop(columns=["GPA", "GradeClass"])

    import os
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    test_data_dir = os.path.join(base_dir, "test_data")
    os.makedirs(test_data_dir, exist_ok=True)
    type1_clean.to_csv(os.path.join(test_data_dir, "type1_clean.csv"), index=False)
    type1_unclean.to_csv(os.path.join(test_data_dir, "type1_unclean.csv"), index=False)
    type2_clean.to_csv(os.path.join(test_data_dir, "type2_clean.csv"), index=False)
    type2_unclean.to_csv(os.path.join(test_data_dir, "type2_unclean.csv"), index=False)

    print("Generated:")
    print(" type1_clean.csv  ", type1_clean.shape)
    print(" type1_unclean.csv", type1_unclean.shape)
    print(" type2_clean.csv  ", type2_clean.shape)
    print(" type2_unclean.csv", type2_unclean.shape)


if __name__ == "__main__":
    main()
