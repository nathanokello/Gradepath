"""
Automated Test Suite for GradePath
Covers all criteria specified in Section 12 of projectinfo.md:
- Type 1 clean & unclean dataset uploads
- Type 2 clean & unclean dataset uploads
- Missing required column detection & clear error
- Non-CSV/XLSX file rejection
- Single-student prediction & out-of-range rejection
- Dashboard views, chart APIs, and CSV downloads
"""

import os
import sys
import io
import json
import unittest
from unittest import mock
import pandas as pd

# Ensure root workspace directory is on sys.path
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from backend.app import app
from backend import database
from backend.session_store import (
    pack_predictions, unpack_predictions, store_analysis, load_analysis,
    default_measure
)
from backend.config import SESSION_ANALYSES_KEY, FULL_PREDICTION_FIELDS

TEST_DATA_DIR = os.path.join(BASE_DIR, "test_data")


class GradePathTestSuite(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        self.client.testing = True

    def test_01_home_page_loads(self):
        """Verify home page loads with 200 OK."""
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Predict a student", response.data)

    def test_02_about_page_explains_architecture_and_tradeoffs(self):
        """Verify the About page is reachable and describes the real storage model."""
        response = self.client.get("/about")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Architecture and data flow", response.data)
        self.assertIn(b"Pros", response.data)
        self.assertIn(b"Cons and limitations", response.data)
        self.assertIn(b"signed session cookie", response.data)
        self.assertIn(b"not encrypted", response.data)
        self.assertIn(b'aria-current="page"', response.data)

    def test_02_predict_valid_student(self):
        """Verify POST /predict returns GPA, grade, range, and feature importances."""
        payload = {
            "StudyTimeWeekly": 9.0,
            "Absences": 4,
            "Tutoring": 1,
            "ParentalSupport": 2,
            "ParentalEducation": 2,
            "Extracurricular": 0,
            "Sports": 1,
            "Music": 0,
            "Volunteering": 0,
        }
        response = self.client.post("/predict", json=payload)
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data["success"])
        self.assertIn("predicted_gpa", data)
        self.assertIn("letter_grade", data)
        self.assertIn("range_min", data)
        self.assertIn("range_max", data)
        self.assertIn("feature_importances", data)
        self.assertGreaterEqual(data["predicted_gpa"], 0.0)
        self.assertLessEqual(data["predicted_gpa"], 4.0)

    def test_03_predict_out_of_range_rejected(self):
        """Verify POST /predict rejects values outside valid range."""
        # Absences = 35 is out of allowed range (0 - 29)
        payload = {
            "StudyTimeWeekly": 9.0,
            "Absences": 35,
            "Tutoring": 1,
            "ParentalSupport": 2,
            "ParentalEducation": 2,
            "Extracurricular": 0,
            "Sports": 1,
            "Music": 0,
            "Volunteering": 0,
        }
        response = self.client.post("/predict", json=payload)
        self.assertEqual(response.status_code, 400)
        data = response.get_json()
        self.assertFalse(data["success"])
        self.assertIn("Absences must be between", data["error"])

    def test_04_predict_missing_feature_rejected(self):
        """Verify POST /predict rejects request missing a feature."""
        payload = {
            "StudyTimeWeekly": 9.0,
            "Absences": 4,
            # Missing remaining features
        }
        response = self.client.post("/predict", json=payload)
        self.assertEqual(response.status_code, 400)
        data = response.get_json()
        self.assertFalse(data["success"])
        self.assertIn("Missing required field", data["error"])

    def test_05_upload_type1_clean(self):
        """Verify type1_clean.csv produces Type 1 analysis with 60 rows out and 0 duplicates."""
        file_path = os.path.join(TEST_DATA_DIR, "type1_clean.csv")
        with open(file_path, "rb") as f:
            data = {"dataset": (f, "type1_clean.csv")}
            response = self.client.post("/upload", data=data, content_type="multipart/form-data")

        self.assertEqual(response.status_code, 200)
        res = response.get_json()
        self.assertTrue(res["success"])
        rep = res["report"]
        self.assertEqual(rep["data_type"], 1)
        self.assertEqual(rep["rows_in"], 60)
        self.assertEqual(rep["rows_out"], 60)
        self.assertEqual(rep["duplicates_removed"], 0)

    def test_06_upload_type1_unclean(self):
        """Verify type1_unclean.csv drops 3 duplicates (63 in -> 60 out) and fixes anomalies."""
        file_path = os.path.join(TEST_DATA_DIR, "type1_unclean.csv")
        with open(file_path, "rb") as f:
            data = {"dataset": (f, "type1_unclean.csv")}
            response = self.client.post("/upload", data=data, content_type="multipart/form-data")

        self.assertEqual(response.status_code, 200)
        res = response.get_json()
        self.assertTrue(res["success"])
        rep = res["report"]
        self.assertEqual(rep["data_type"], 1)
        self.assertEqual(rep["rows_in"], 63)
        self.assertEqual(rep["rows_out"], 60)
        self.assertEqual(rep["duplicates_removed"], 3)
        self.assertGreater(rep["values_fixed"], 0)

    def test_07_upload_type2_clean(self):
        """Verify type2_clean.csv produces Type 2 analysis with accuracy calculated."""
        file_path = os.path.join(TEST_DATA_DIR, "type2_clean.csv")
        with open(file_path, "rb") as f:
            data = {"dataset": (f, "type2_clean.csv")}
            response = self.client.post("/upload", data=data, content_type="multipart/form-data")

        self.assertEqual(response.status_code, 200)
        res = response.get_json()
        self.assertTrue(res["success"])
        self.assertEqual(res["report"]["data_type"], 2)
        analysis_id = res["analysis_id"]

        # Verify DB record
        analysis = database.get_analysis_by_id(analysis_id)
        self.assertIsNotNone(analysis["grade_accuracy"])
        self.assertGreaterEqual(analysis["grade_accuracy"], 0.0)

    def test_08_upload_type2_unclean(self):
        """Verify type2_unclean.csv handles duplicates and anomaly cleaning."""
        file_path = os.path.join(TEST_DATA_DIR, "type2_unclean.csv")
        with open(file_path, "rb") as f:
            data = {"dataset": (f, "type2_unclean.csv")}
            response = self.client.post("/upload", data=data, content_type="multipart/form-data")

        self.assertEqual(response.status_code, 200)
        res = response.get_json()
        self.assertTrue(res["success"])
        rep = res["report"]
        self.assertEqual(rep["data_type"], 2)
        self.assertEqual(rep["rows_in"], 63)
        self.assertEqual(rep["rows_out"], 60)
        self.assertEqual(rep["duplicates_removed"], 3)

    def test_09_upload_missing_column_rejected(self):
        """Verify file missing required columns is rejected with informative error."""
        bad_df = pd.DataFrame({
            "StudyTimeWeekly": [10.0],
            "Tutoring": [1],
        })
        csv_bytes = io.BytesIO(bad_df.to_csv(index=False).encode("utf-8"))
        data = {"dataset": (csv_bytes, "missing_cols.csv")}
        response = self.client.post("/upload", data=data, content_type="multipart/form-data")

        self.assertEqual(response.status_code, 400)
        res = response.get_json()
        self.assertFalse(res["success"])
        self.assertIn("missing required columns", res["error"].lower())

    def test_10_upload_invalid_file_extension(self):
        """Verify non-CSV/XLSX file is rejected."""
        txt_bytes = io.BytesIO(b"Hello world test")
        data = {"dataset": (txt_bytes, "notes.txt")}
        response = self.client.post("/upload", data=data, content_type="multipart/form-data")

        self.assertEqual(response.status_code, 400)
        res = response.get_json()
        self.assertFalse(res["success"])
        self.assertIn("Invalid file format", res["error"])

    def test_11_dashboard_and_chart_api(self):
        """Verify dashboard view, chart API, and CSV export."""
        latest_id = database.get_latest_analysis_id()
        self.assertIsNotNone(latest_id)

        # GET /dashboard redirects to /dashboard/<latest_id>
        dash_res = self.client.get("/dashboard", follow_redirects=True)
        self.assertEqual(dash_res.status_code, 200)
        self.assertIn(b"Visualization dashboard", dash_res.data)

        # GET /api/dashboard/<id> returns Plotly data structures
        api_res = self.client.get(f"/api/dashboard/{latest_id}")
        self.assertEqual(api_res.status_code, 200)
        api_data = api_res.get_json()
        self.assertIn("predicted_gpas", api_data)
        self.assertIn("grade_counts", api_data)
        self.assertIn("feature_importances", api_data)

        # GET /download/<id>.csv returns downloadable CSV
        dl_res = self.client.get(f"/download/{latest_id}.csv")
        self.assertEqual(dl_res.status_code, 200)
        self.assertEqual(dl_res.mimetype, "text/csv")
        self.assertIn(b"PredictedGPA", dl_res.data)

    def test_12_upload_mirrors_analysis_into_session_cookie(self):
        """Verify an upload is mirrored into the signed session cookie."""
        file_path = os.path.join(TEST_DATA_DIR, "type2_clean.csv")
        with open(file_path, "rb") as f:
            data = {"dataset": (f, "type2_clean.csv")}
            response = self.client.post(
                "/upload", data=data, content_type="multipart/form-data"
            )

        self.assertEqual(response.status_code, 200)
        analysis_id = response.get_json()["analysis_id"]

        with self.client.session_transaction() as sess:
            entries = sess.get(SESSION_ANALYSES_KEY, [])
            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0]["id"], analysis_id)
            self.assertEqual(entries[0]["fields"], FULL_PREDICTION_FIELDS)
            self.assertEqual(entries[0]["meta"]["filename"], "type2_clean.csv")

    def test_13_dashboard_survives_a_database_without_the_analysis(self):
        """Verify the dashboard renders from the session when the DB has no copy.

        This mirrors the Vercel behaviour where the next request can land on an
        instance whose ephemeral SQLite never saw the upload.
        """
        file_path = os.path.join(TEST_DATA_DIR, "type1_clean.csv")
        with open(file_path, "rb") as f:
            data = {"dataset": (f, "type1_clean.csv")}
            response = self.client.post(
                "/upload", data=data, content_type="multipart/form-data"
            )
        analysis_id = response.get_json()["analysis_id"]

        with mock.patch.object(database, "get_analysis_by_id", return_value=None), \
             mock.patch.object(database, "get_latest_analysis_id", return_value=None):
            dash_res = self.client.get(f"/dashboard/{analysis_id}")
            self.assertEqual(dash_res.status_code, 200)
            self.assertIn(b"Visualization dashboard", dash_res.data)
            self.assertIn(b"type1_clean.csv", dash_res.data)

            api_res = self.client.get(f"/api/dashboard/{analysis_id}")
            self.assertEqual(api_res.status_code, 200)
            self.assertEqual(len(api_res.get_json()["predicted_gpas"]), 60)

            dl_res = self.client.get(f"/download/{analysis_id}.csv")
            self.assertEqual(dl_res.status_code, 200)
            self.assertIn(b"PredictedGPA", dl_res.data)

    def test_14_empty_dashboard_shows_preview_cards_not_an_upload_panel(self):
        """Verify the dashboard empty state reads as analytics, not a second upload page."""
        fresh_client = app.test_client()
        fresh_client.testing = True

        with mock.patch.object(database, "get_latest_analysis_id", return_value=None), \
             mock.patch.object(database, "get_all_analyses", return_value=[]):
            response = fresh_client.get("/dashboard")

        self.assertEqual(response.status_code, 200)
        body = response.data.decode("utf-8")
        self.assertIn("ghost-grid", body)
        self.assertIn("ghost-card", body)
        self.assertNotIn("No datasets have been analyzed", body)
        self.assertNotIn("Upload a Dataset", body)
        # A single, quiet call to action is still allowed.
        self.assertIn("Analyze a dataset", body)

    def test_15_store_analysis_downgrades_to_fit_the_cookie_budget(self):
        """Verify oversized payloads are reduced and truncated instead of dropped."""
        rows = []
        for index in range(600):
            rows.append({
                "student_row": index + 1,
                "study_time": 12.34,
                "absences": index % 20,
                "tutoring": index % 2,
                "parental_support": index % 5,
                "parental_education": index % 5,
                "extracurricular": index % 2,
                "sports": index % 2,
                "music": index % 2,
                "volunteering": index % 2,
                "predicted_gpa": 3.21,
                "predicted_grade": "B",
                "actual_gpa": 3.10,
                "actual_grade": "B",
            })

        session_data = {}
        mode = store_analysis(session_data, 1, {"filename": "big.csv"}, rows)

        self.assertIn(mode, ("reduced", "full"))
        entries = session_data[SESSION_ANALYSES_KEY]
        self.assertEqual(len(entries), 1)
        self.assertLessEqual(default_measure(session_data), 3800)

        meta, restored = load_analysis(session_data, 1)
        self.assertTrue(restored)
        # Every restored row keeps the same column shape, including the
        # columns that were dropped when the payload was downgraded.
        for row in restored:
            self.assertIn("parental_education", row)
            self.assertIn("volunteering", row)
            self.assertEqual(row["predicted_grade"], "B")

    def test_17_csv_export_prefers_the_database_copy_when_the_session_is_trimmed(self):
        """Verify a trimmed session payload does not truncate the CSV export.

        The session cookie may only hold a subset of the rows, but the CSV
        export should still contain every prediction row while the database
        copy for the same analysis is reachable.
        """
        file_path = os.path.join(TEST_DATA_DIR, "type1_clean.csv")
        with open(file_path, "rb") as f:
            data = {"dataset": (f, "type1_clean.csv")}
            response = self.client.post(
                "/upload", data=data, content_type="multipart/form-data"
            )
        analysis_id = response.get_json()["analysis_id"]

        # Shrink the session payload so it really only holds a few rows.
        with self.client.session_transaction() as sess:
            entries = sess.get(SESSION_ANALYSES_KEY, [])
            entry = entries[0]
            rows = unpack_predictions(entry["rows"], entry["fields"])
            entry["rows"] = pack_predictions(rows[:5], entry["fields"])
            entry["meta"]["truncated"] = True
            entry["meta"]["rows_stored"] = 5
            sess[SESSION_ANALYSES_KEY] = entries

        # The session copy holds fewer rows than the database copy.
        db_rows = database.get_predictions_by_analysis_id(analysis_id)
        self.assertEqual(len(db_rows), 60)
        with mock.patch.object(
            database, "get_predictions_by_analysis_id", return_value=db_rows
        ) as mocked:
            dl_res = self.client.get(f"/download/{analysis_id}.csv")
        self.assertEqual(dl_res.status_code, 200)
        mocked.assert_called_once_with(analysis_id)

        lines = dl_res.data.decode("utf-8").strip().splitlines()
        self.assertEqual(len(lines), 61)  # header + all 60 student rows

    def test_18_csv_export_falls_back_to_the_trimmed_session_copy(self):
        """Verify the export still works when the database copy is gone."""
        file_path = os.path.join(TEST_DATA_DIR, "type1_clean.csv")
        with open(file_path, "rb") as f:
            data = {"dataset": (f, "type1_clean.csv")}
            response = self.client.post(
                "/upload", data=data, content_type="multipart/form-data"
            )
        analysis_id = response.get_json()["analysis_id"]

        # Shrink the session payload so it really only holds a few rows.
        with self.client.session_transaction() as sess:
            entries = sess.get(SESSION_ANALYSES_KEY, [])
            entry = entries[0]
            rows = unpack_predictions(entry["rows"], entry["fields"])
            entry["rows"] = pack_predictions(rows[:5], entry["fields"])
            entry["meta"]["truncated"] = True
            entry["meta"]["rows_stored"] = 5
            sess[SESSION_ANALYSES_KEY] = entries

        with mock.patch.object(database, "get_analysis_by_id", return_value=None):
            dl_res = self.client.get(f"/download/{analysis_id}.csv")

        self.assertEqual(dl_res.status_code, 200)
        lines = dl_res.data.decode("utf-8").strip().splitlines()
        self.assertEqual(len(lines), 6)  # header + 5 trimmed student rows
        self.assertIn("PredictedGPA", lines[0])

    def test_16_unpack_restores_placeholder_columns_for_every_row(self):
        """Verify reduced payloads restore dropped columns on all rows."""
        fields = [
            "student_row", "study_time", "absences", "tutoring",
            "parental_support", "predicted_gpa", "predicted_grade",
        ]
        rows = [
            {
                "student_row": i + 1,
                "study_time": 5.0,
                "absences": 1,
                "tutoring": 0,
                "parental_support": 2,
                "predicted_gpa": 2.5,
                "predicted_grade": "C",
            }
            for i in range(4)
        ]

        blob = pack_predictions(rows, fields)
        restored = unpack_predictions(blob, fields)

        self.assertEqual(len(restored), 4)
        for row in restored:
            self.assertEqual(row["parental_education"], "")
            self.assertEqual(row["music"], "")
            self.assertEqual(row["student_row"], row["student_row"])
            self.assertIsInstance(row["study_time"], float)
            self.assertIsInstance(row["absences"], int)


if __name__ == "__main__":
    unittest.main()
