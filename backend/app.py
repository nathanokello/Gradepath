"""
GradePath: Student Performance Prediction System
Main Flask application routing and controller logic.
"""

import os
import sys
import io
import csv
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
from flask import (
    Flask, render_template, request, jsonify, redirect, url_for, Response, session
)

# Anchor paths to project root
BACKEND_DIR = os.path.abspath(os.path.dirname(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(BACKEND_DIR, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

try:
    from backend.config import (
        VALID_RANGES, FEATURE_COLUMNS, MAX_FILE_SIZE, ALLOWED_EXTENSIONS,
        SECRET_KEY, SESSION_LIFETIME_DAYS, SESSION_ANALYSES_KEY
    )
    from backend.clean_data import clean_dataframe
    from backend.model_service import model_service
    from backend.session_store import (
        store_analysis, load_analysis, list_stored_analyses,
        latest_stored_analysis_id
    )
    import backend.database as database
except ImportError:
    from config import (
        VALID_RANGES, FEATURE_COLUMNS, MAX_FILE_SIZE, ALLOWED_EXTENSIONS,
        SECRET_KEY, SESSION_LIFETIME_DAYS, SESSION_ANALYSES_KEY
    )
    from clean_data import clean_dataframe
    from model_service import model_service
    from session_store import (
        store_analysis, load_analysis, list_stored_analyses,
        latest_stored_analysis_id
    )
    import database

# Point template_folder and static_folder to the project root directories
app = Flask(
    __name__,
    template_folder=os.path.join(PROJECT_ROOT, "templates"),
    static_folder=(
        None if os.environ.get("VERCEL")
        else os.path.join(PROJECT_ROOT, "static")
    ),
)
if os.environ.get("VERCEL"):
    # Vercel serves these URLs directly from the public directory.
    app.add_url_rule("/static/<path:filename>", endpoint="static", build_only=True)
app.config["MAX_CONTENT_LENGTH"] = MAX_FILE_SIZE

# Session configuration: the signed cookie carries the analysis payloads so
# they survive across serverless instances that do not share a database.
app.secret_key = SECRET_KEY
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=SESSION_LIFETIME_DAYS)
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
# Secure cookies only make sense behind HTTPS; enabling them unconditionally
# would break the plain-HTTP local development server.
app.config["SESSION_COOKIE_SECURE"] = bool(os.environ.get("VERCEL"))

# Initialize the SQLite database on startup
database.init_db()


def _cookie_size(session_dict):
    """
    Returns the exact number of bytes the session cookie would occupy.

    Flask signs the session with itsdangerous, so the real size is only known
    after serialization. Measuring the signed payload accounts for zlib
    compression, base64 expansion and the appended timestamp/signature.
    """
    serializer = app.session_interface.get_signing_serializer(app)
    if serializer is None:
        return len(str(session_dict).encode("utf-8"))
    return len(serializer.dumps(dict(session_dict)))


def _resolve_analysis(analysis_id):
    """
    Returns (metadata, prediction_rows) for an analysis.

    The session copy wins over the database copy. On Vercel every instance
    keeps its own SQLite file with its own auto-increment sequence, so the
    same numeric id can point at a completely different upload on another
    instance. The browser's own session copy is therefore authoritative and
    the database is only used as a fallback.
    """
    stored = load_analysis(session, analysis_id)
    if stored is not None:
        meta, rows = stored
        return meta, rows

    analysis = database.get_analysis_by_id(analysis_id)
    if not analysis:
        return None, None

    return analysis, database.get_predictions_by_analysis_id(analysis_id)


def _resolve_analysis_for_export(analysis_id):
    """
    Returns (metadata, prediction_rows) for a CSV export.

    The session copy wins over the database copy. On Vercel every instance
    keeps its own SQLite file with its own auto-increment sequence, so the
    same numeric id can point at a completely different upload on another
    instance. The browser's own session copy is therefore authoritative and
    the database is only used as a fallback.

    The one exception is a session payload that was trimmed to fit the cookie
    budget. When the matching database row is still reachable it holds every
    prediction row, so the export uses it instead of the trimmed subset. The
    filename is compared as well so an id collision on another instance can
    never pull in a different dataset.
    """
    stored = load_analysis(session, analysis_id)
    if stored is None:
        return _resolve_analysis(analysis_id)

    meta, rows = stored
    if not meta.get("truncated"):
        return meta, rows

    analysis = database.get_analysis_by_id(analysis_id)
    if not analysis or analysis.get("filename") != meta.get("filename"):
        return meta, rows

    return analysis, database.get_predictions_by_analysis_id(analysis_id)


def _analysis_index():
    """
    Returns the list shown in the "reopen past analysis" dropdown.

    Session entries come first (newest first) followed by the database rows,
    without duplicating ids that are already present in the session.
    """
    entries = list_stored_analyses(session)
    seen = {entry.get("id") for entry in entries}
    for item in database.get_all_analyses():
        if item.get("id") not in seen:
            entries.append(item)
    return entries


@app.route("/")
def home():
    """
    Renders the Predict home page with the single-student prediction form.
    """
    return render_template("index.html", active_page="predict")


@app.route("/predict", methods=["POST"])
def predict():
    """
    Accepts JSON input for a single student, validates ranges,
    and returns predicted GPA, grade, confidence range, and feature importances.
    """
    data = request.get_json()
    if not data:
        return jsonify({"success": False, "error": "No input data provided."}), 400

    # Validate each input feature against allowed ranges
    for field, rule in VALID_RANGES.items():
        if field not in data:
            return jsonify({
                "success": False,
                "error": f"Missing required field: {field}"
            }), 400

        try:
            val = rule["type"](data[field])
        except (ValueError, TypeError):
            return jsonify({
                "success": False,
                "error": f"Invalid format for {field}."
            }), 400

        if val < rule["min"] or val > rule["max"]:
            return jsonify({
                "success": False,
                "error": f"{field} must be between {rule['min']} and {rule['max']}."
            }), 400

    try:
        # Run model inference
        result = model_service.predict_single(data)
        result["success"] = True
        return jsonify(result)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/upload", methods=["GET"])
def upload_page():
    """
    Renders the dataset upload page.
    """
    return render_template("upload.html", active_page="upload")


@app.route("/upload", methods=["POST"])
def upload_file():
    """
    Handles CSV/Excel file uploads.
    Cleans dataset using clean_data.py, predicts batch GPAs,
    records results in SQLite, and returns analysis ID with cleaning report.
    """
    if "dataset" not in request.files:
        return jsonify({"success": False, "error": "No file uploaded."}), 400

    file = request.files["dataset"]
    filename = file.filename or ""

    # Check file extension
    file_ext = os.path.splitext(filename)[1].lower()
    if file_ext not in ALLOWED_EXTENSIONS:
        return jsonify({
            "success": False,
            "error": "Invalid file format. Only .csv and .xlsx are supported."
        }), 400

    # Read uploaded file into pandas
    try:
        if file_ext == ".csv":
            raw_df = pd.read_csv(file)
        else:
            raw_df = pd.read_excel(file)
    except Exception as e:
        return jsonify({
            "success": False,
            "error": f"Could not read file: {str(e)}"
        }), 400

    if raw_df.empty:
        return jsonify({"success": False, "error": "The uploaded file is empty."}), 400

    # Detect Type 1 vs Type 2 based on whether GPA or GradeClass is present
    normalized_cols = {str(c).strip().lower(): c for c in raw_df.columns}
    has_gpa = "gpa" in normalized_cols
    has_gradeclass = "gradeclass" in normalized_cols
    data_type = 2 if (has_gpa or has_gradeclass) else 1

    # Preserve actual GPA/grade values for Type 2 evaluation
    actual_gpa_series = None
    actual_grade_series = None

    if has_gpa:
        gpa_col = normalized_cols["gpa"]
        actual_gpa_series = pd.to_numeric(raw_df[gpa_col], errors="coerce")
        actual_grade_series = [
            model_service.gpa_to_grade(g)[0] if pd.notna(g) else None
            for g in actual_gpa_series
        ]
    elif has_gradeclass:
        gc_col = normalized_cols["gradeclass"]
        class_map = {0: "A", 1: "B", 2: "C", 3: "D", 4: "F"}
        numeric_gc = pd.to_numeric(raw_df[gc_col], errors="coerce")
        actual_grade_series = [
            class_map.get(int(c)) if pd.notna(c) and int(c) in class_map else None
            for c in numeric_gc
        ]

    # Clean the dataframe according to project rules
    try:
        cleaned_df, report = clean_dataframe(raw_df)
    except ValueError as err:
        return jsonify({"success": False, "error": str(err)}), 400
    except Exception as err:
        return jsonify({
            "success": False,
            "error": f"Cleaning error: {str(err)}"
        }), 400

    # Predict for each student in the cleaned dataset
    try:
        predicted_df = model_service.predict_batch(cleaned_df)
    except Exception as err:
        return jsonify({
            "success": False,
            "error": f"Prediction error: {str(err)}"
        }), 500

    avg_gpa = round(float(predicted_df["predicted_gpa"].mean()), 2)

    # Compute accuracy for Type 2 datasets
    grade_accuracy = None
    if data_type == 2 and actual_grade_series is not None:
        # Align with cleaned rows (duplicates removed from original)
        cleaned_indices = cleaned_df.index
        eval_actual = [actual_grade_series[i] for i in cleaned_indices if i < len(actual_grade_series)]
        eval_pred = list(predicted_df["predicted_grade"])

        matches = sum(1 for p, a in zip(eval_pred, eval_actual) if p == a and a is not None)
        total = sum(1 for a in eval_actual if a is not None)
        if total > 0:
            grade_accuracy = round((matches / total) * 100, 1)

    # Calculate total values fixed across all columns
    values_fixed_dict = report.get("values_fixed", {})
    total_values_fixed = sum(values_fixed_dict.values()) if isinstance(values_fixed_dict, dict) else 0

    # Prepare database metadata
    metadata = {
        "filename": filename,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "data_type": data_type,
        "rows_in": report["rows_in"],
        "rows_out": report["rows_out"],
        "duplicates_removed": report["duplicates_removed"],
        "values_fixed": total_values_fixed,
        "avg_gpa": avg_gpa,
        "grade_accuracy": grade_accuracy,
    }

    # Prepare student prediction rows
    predictions_rows = []
    for idx, row in predicted_df.iterrows():
        # Match actual values if Type 2
        act_gpa = None
        act_grade = None
        if data_type == 2:
            if actual_gpa_series is not None and idx < len(actual_gpa_series):
                g_val = actual_gpa_series[idx]
                act_gpa = round(float(g_val), 2) if pd.notna(g_val) else None
            if actual_grade_series is not None and idx < len(actual_grade_series):
                act_grade = actual_grade_series[idx]

        predictions_rows.append({
            "student_row": idx + 1,
            "study_time": round(float(row["StudyTimeWeekly"]), 2),
            "absences": int(row["Absences"]),
            "tutoring": int(row["Tutoring"]),
            "parental_support": int(row["ParentalSupport"]),
            "parental_education": int(row["ParentalEducation"]),
            "extracurricular": int(row["Extracurricular"]),
            "sports": int(row["Sports"]),
            "music": int(row["Music"]),
            "volunteering": int(row["Volunteering"]),
            "predicted_gpa": round(float(row["predicted_gpa"]), 2),
            "predicted_grade": str(row["predicted_grade"]),
            "actual_gpa": act_gpa,
            "actual_grade": act_grade,
        })

    # Save to SQLite
    analysis_id = database.insert_analysis(metadata, predictions_rows)

    # Mirror the analysis into the signed session cookie. The database copy
    # lives on the instance that handled the upload and is not visible to the
    # other instances serving the next request on Vercel.
    session.permanent = True
    store_analysis(
        session,
        analysis_id,
        dict(metadata, id=analysis_id),
        predictions_rows,
        measure=_cookie_size,
    )

    return jsonify({
        "success": True,
        "analysis_id": analysis_id,
        "redirect_url": url_for("dashboard_detail", analysis_id=analysis_id),
        "report": {
            "filename": filename,
            "data_type": data_type,
            "rows_in": report["rows_in"],
            "rows_out": report["rows_out"],
            "duplicates_removed": report["duplicates_removed"],
            "values_fixed": total_values_fixed,
            "columns_count": len(raw_df.columns),
        }
    })


@app.route("/dashboard")
def dashboard_latest():
    """
    Redirects to the latest analysis or shows an empty dashboard if none exist.
    """
    latest_id = latest_stored_analysis_id(session) or database.get_latest_analysis_id()
    if latest_id:
        return redirect(url_for("dashboard_detail", analysis_id=latest_id))
    return render_template("dashboard.html", analysis=None, active_page="dashboard")


@app.route("/dashboard/<int:analysis_id>")
def dashboard_detail(analysis_id):
    """
    Renders the dashboard for a specific analysis ID.
    """
    analysis, predictions = _resolve_analysis(analysis_id)
    if not analysis:
        return redirect(url_for("dashboard_latest"))

    all_analyses = _analysis_index()

    # Students at risk (predicted letter grade D or F)
    at_risk_count = sum(1 for p in predictions if p["predicted_grade"] in ("D", "F"))

    return render_template(
        "dashboard.html",
        analysis=analysis,
        predictions=predictions,
        all_analyses=all_analyses,
        at_risk_count=at_risk_count,
        active_page="dashboard",
    )


@app.route("/api/dashboard/<int:analysis_id>")
def api_dashboard_data(analysis_id):
    """
    Returns pre-aggregated JSON chart data for Plotly on the client.
    """
    analysis, predictions = _resolve_analysis(analysis_id)
    if not analysis:
        return jsonify({"error": "Analysis not found"}), 404

    predicted_gpas = [p["predicted_gpa"] for p in predictions]
    absences = [p["absences"] for p in predictions]

    # Grade counts
    grade_counts = {"A": 0, "B": 0, "C": 0, "D": 0, "F": 0}
    for p in predictions:
        g = p["predicted_grade"]
        if g in grade_counts:
            grade_counts[g] += 1

    # Linear trendline for Absences vs Predicted GPA
    trendline = None
    if len(absences) > 1:
        x_arr = np.array(absences, dtype=float)
        y_arr = np.array(predicted_gpas, dtype=float)
        slope, intercept = np.polyfit(x_arr, y_arr, 1)
        x_min, x_max = 0.0, 29.0
        trendline = {
            "x": [x_min, x_max],
            "y": [round(float(slope * x_min + intercept), 2), round(float(slope * x_max + intercept), 2)],
        }

    # Confusion matrix and actual comparisons for Type 2
    confusion_matrix = None
    actual_gpas = []
    if analysis["data_type"] == 2:
        labels = ["A", "B", "C", "D", "F"]
        confusion_matrix = {act: {pred: 0 for pred in labels} for act in labels}

        for p in predictions:
            if p["actual_gpa"] is not None:
                actual_gpas.append(p["actual_gpa"])
            act = p["actual_grade"]
            pred = p["predicted_grade"]
            if act in confusion_matrix and pred in confusion_matrix[act]:
                confusion_matrix[act][pred] += 1

    return jsonify({
        "predicted_gpas": predicted_gpas,
        "absences": absences,
        "grade_counts": grade_counts,
        "feature_importances": model_service.get_global_feature_importances(),
        "trendline": trendline,
        "confusion_matrix": confusion_matrix,
        "actual_gpas": actual_gpas,
    })


@app.route("/download/<int:analysis_id>.csv")
def download_csv(analysis_id):
    """
    Streams predictions for an analysis as a downloadable CSV.
    """
    analysis, predictions = _resolve_analysis_for_export(analysis_id)
    if not analysis:
        return "Analysis not found", 404

    output = io.StringIO()
    writer = csv.writer(output)

    # Header columns
    headers = [
        "StudentID", "StudyTimeWeekly", "Absences", "Tutoring",
        "ParentalSupport", "ParentalEducation", "Extracurricular",
        "Sports", "Music", "Volunteering", "PredictedGPA", "PredictedGrade"
    ]
    if analysis["data_type"] == 2:
        headers.extend(["ActualGPA", "ActualGrade"])
    writer.writerow(headers)

    # Data rows
    for p in predictions:
        row = [
            p["student_row"],
            p["study_time"],
            p["absences"],
            p["tutoring"],
            p["parental_support"],
            p["parental_education"],
            p["extracurricular"],
            p["sports"],
            p["music"],
            p["volunteering"],
            p["predicted_gpa"],
            p["predicted_grade"],
        ]
        if analysis["data_type"] == 2:
            row.extend([
                p["actual_gpa"] if p["actual_gpa"] is not None else "",
                p["actual_grade"] if p["actual_grade"] is not None else "",
            ])
        writer.writerow(row)

    output.seek(0)
    filename = f"gradepath_analysis_{analysis_id}.csv"
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


if __name__ == "__main__":
    app.run(debug=True, port=5000)

