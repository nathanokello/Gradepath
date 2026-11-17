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
import unittest
import pandas as pd

# Ensure root workspace directory is on sys.path
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from backend.app import app
from backend import database

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


if __name__ == "__main__":
    unittest.main()
