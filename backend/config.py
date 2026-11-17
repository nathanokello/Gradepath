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
