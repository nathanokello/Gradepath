"""
Configuration settings for the GradePath application.
Contains paths, feature lists, valid value ranges, and grade cutoff rules.
"""

import os
import json
import tempfile

# Base paths: anchored to the project root (one level up from backend/)
BACKEND_DIR = os.path.abspath(os.path.dirname(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(BACKEND_DIR, ".."))

MODEL_DIR = os.path.join(PROJECT_ROOT, "model")
MODEL_PATH = os.path.join(MODEL_DIR, "student_performance_modelv2.joblib")
if os.environ.get("GRADEPATH_DB_PATH"):
    DB_PATH = os.environ["GRADEPATH_DB_PATH"]
elif os.environ.get("VERCEL"):
    DB_PATH = os.path.join(tempfile.gettempdir(), "gradepath.db")
else:
    DB_PATH = os.path.join(PROJECT_ROOT, "gradepath.db")

# Fallback or specific cutoffs file
CUTOFFS_FILE_V2 = os.path.join(MODEL_DIR, "grade_cutoffsv2.json")
CUTOFFS_FILE_DEFAULT = os.path.join(MODEL_DIR, "grade_cutoffs.json")

# Model input features in the exact required order
FEATURE_COLUMNS = [
    "StudyTimeWeekly",
    "Absences",
    "Tutoring",
    "ParentalSupport",
    "ParentalEducation",
    "Extracurricular",
    "Sports",
    "Music",
    "Volunteering",
]

# Valid ranges and types for form and file validation
VALID_RANGES = {
    "StudyTimeWeekly": {"min": 0.0, "max": 20.0, "type": float},
    "Absences": {"min": 0, "max": 29, "type": int},
    "Tutoring": {"min": 0, "max": 1, "type": int},
    "ParentalSupport": {"min": 0, "max": 4, "type": int},
    "ParentalEducation": {"min": 0, "max": 4, "type": int},
    "Extracurricular": {"min": 0, "max": 1, "type": int},
    "Sports": {"min": 0, "max": 1, "type": int},
    "Music": {"min": 0, "max": 1, "type": int},
    "Volunteering": {"min": 0, "max": 1, "type": int},
}

# Human-readable labels for dropdown options
PARENTAL_SUPPORT_LABELS = {
    0: "None",
    1: "Low",
    2: "Moderate",
    3: "High",
    4: "Very high",
}

PARENTAL_EDUCATION_LABELS = {
    0: "None",
    1: "High school",
    2: "Some college",
    3: "Bachelor's",
    4: "Higher",
}

# Grade mapping from GPA to Letter Grade and GradeClass
GRADE_BANDS = [
    {"grade": "A", "class_id": 0, "min_gpa": 3.5, "max_gpa": 4.0},
    {"grade": "B", "class_id": 1, "min_gpa": 3.0, "max_gpa": 3.4999},
    {"grade": "C", "class_id": 2, "min_gpa": 2.5, "max_gpa": 2.9999},
    {"grade": "D", "class_id": 3, "min_gpa": 2.0, "max_gpa": 2.4999},
    {"grade": "F", "class_id": 4, "min_gpa": 0.0, "max_gpa": 1.9999},
]

# Static benchmark facts from training (Section 4 of projectinfo.md)
MODEL_METRICS = {
    "r2": 0.9306,
    "mae": 0.1869,
    "rmse": 0.2395,
    "grade_accuracy": 73.3,
    "baseline_accuracy": 66.0,
}

# Upload constraints
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 Megabytes
ALLOWED_EXTENSIONS = {".csv", ".xlsx"}

# ---------------------------------------------------------------------------
# Session / cookie-backed persistence settings
#
# On Vercel every serverless instance gets its own ephemeral SQLite file in
# /tmp, so an upload written by one instance is invisible to the next request.
# To keep the dashboard populated, the analysis payload is mirrored into the
# Flask signed-session cookie, which travels with the browser.
# ---------------------------------------------------------------------------

# The signing key must be identical on every instance, otherwise cookies
# signed by one instance cannot be verified by another. Prefer the SECRET_KEY
# environment variable; the constant below is a deterministic fallback so the
# app still works on an unclaimed Vercel project.
SECRET_KEY = os.environ.get("SECRET_KEY") or (
    "gradepath-static-session-key-3f9a1c7e5b2d8046f1a9c3e7d5b08126"
)

# Maximum size (bytes) of the encoded session cookie payload. Browsers cap a
# single cookie at roughly 4096 bytes, so stay comfortably below that.
SESSION_COOKIE_MAX_BYTES = 3800

# How long a browser keeps the stored analyses.
SESSION_LIFETIME_DAYS = 7

# Key under which the analysis payloads are kept in the Flask session.
SESSION_ANALYSES_KEY = "gradepath_analyses"

# Every field of a prediction row, in the order used by the CSV encoding.
FULL_PREDICTION_FIELDS = [
    "student_row",
    "study_time",
    "absences",
    "tutoring",
    "parental_support",
    "parental_education",
    "extracurricular",
    "sports",
    "music",
    "volunteering",
    "predicted_gpa",
    "predicted_grade",
    "actual_gpa",
    "actual_grade",
]

# Fields kept when the full set does not fit inside the cookie budget. These
# are exactly the columns the dashboard renders; the remaining ones are
# exported as empty strings so the CSV schema stays stable.
REDUCED_PREDICTION_FIELDS = [
    "student_row",
    "study_time",
    "absences",
    "tutoring",
    "parental_support",
    "predicted_gpa",
    "predicted_grade",
    "actual_gpa",
    "actual_grade",
]
