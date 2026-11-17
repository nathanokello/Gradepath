"""
Database helper functions using Python's built-in sqlite3 module.
Provides clean, parameterized operations for storing and fetching batch analyses.
"""

import sqlite3
from datetime import datetime
try:
    from backend.config import DB_PATH
except ImportError:
    from config import DB_PATH


def get_db_connection():
    """
    Creates and returns a connection to the SQLite database.
    Configures row_factory so columns can be accessed by name.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """
    Creates the required database tables if they do not already exist.
    Called once when the Flask application starts up.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    # Analyses table: stores metadata and summary for each uploaded dataset
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS analyses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        filename TEXT NOT NULL,
        created_at TEXT NOT NULL,
        data_type INTEGER NOT NULL,
        rows_in INTEGER,
        rows_out INTEGER,
        duplicates_removed INTEGER,
        values_fixed INTEGER,
        avg_gpa REAL,
        grade_accuracy REAL
    );
    """)

    # Predictions table: stores individual student rows from an analysis
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS predictions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        analysis_id INTEGER NOT NULL REFERENCES analyses(id),
        student_row INTEGER,
        study_time REAL,
        absences INTEGER,
        tutoring INTEGER,
        parental_support INTEGER,
        parental_education INTEGER,
        extracurricular INTEGER,
        sports INTEGER,
        music INTEGER,
        volunteering INTEGER,
        predicted_gpa REAL,
        predicted_grade TEXT,
        actual_gpa REAL,
        actual_grade TEXT
    );
    """)

    conn.commit()
    conn.close()


def insert_analysis(metadata, predictions_rows):
    """
    Inserts a new analysis record and all associated student prediction rows.
    Uses parameterized '?' placeholders for safety.
    Returns the new analysis id.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    created_at = datetime.now().strftime("%Y-%m-%d %H:%M")

    cursor.execute("""
        INSERT INTO analyses (
            filename, created_at, data_type, rows_in, rows_out,
            duplicates_removed, values_fixed, avg_gpa, grade_accuracy
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        metadata["filename"],
        created_at,
        metadata["data_type"],
        metadata["rows_in"],
        metadata["rows_out"],
        metadata["duplicates_removed"],
        metadata["values_fixed"],
        metadata["avg_gpa"],
        metadata["grade_accuracy"],
    ))

    analysis_id = cursor.lastrowid

    # Prepare rows for batch insert
    batch_data = []
    for row in predictions_rows:
        batch_data.append((
            analysis_id,
            row.get("student_row"),
            row.get("study_time"),
            row.get("absences"),
            row.get("tutoring"),
            row.get("parental_support"),
            row.get("parental_education"),
            row.get("extracurricular"),
            row.get("sports"),
            row.get("music"),
            row.get("volunteering"),
            row.get("predicted_gpa"),
            row.get("predicted_grade"),
            row.get("actual_gpa"),
            row.get("actual_grade"),
        ))

    cursor.executemany("""
        INSERT INTO predictions (
            analysis_id, student_row, study_time, absences, tutoring,
            parental_support, parental_education, extracurricular, sports,
            music, volunteering, predicted_gpa, predicted_grade,
            actual_gpa, actual_grade
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, batch_data)

    conn.commit()
    conn.close()
    return analysis_id


def get_all_analyses():
    """
    Returns a list of all saved analyses for the dashboard dropdown,
    ordered from newest to oldest.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, filename, created_at, data_type, rows_out, avg_gpa, grade_accuracy
        FROM analyses
        ORDER BY id DESC
    """)
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_latest_analysis_id():
    """
    Returns the ID of the most recent analysis, or None if no analyses exist.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM analyses ORDER BY id DESC LIMIT 1")
    row = cursor.fetchone()
    conn.close()
    return row["id"] if row else None


def get_analysis_by_id(analysis_id):
    """
    Fetches the metadata for a single analysis by its ID.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM analyses WHERE id = ?", (analysis_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def get_predictions_by_analysis_id(analysis_id):
    """
    Fetches all prediction records for a given analysis ID.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM predictions
        WHERE analysis_id = ?
        ORDER BY student_row ASC
    """, (analysis_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

