"""
Handles loading the trained Random Forest model and running predictions.
Also converts numeric GPA values into letter grades.
"""

import os
import joblib
import numpy as np
import pandas as pd
try:
    from backend.config import MODEL_PATH, FEATURE_COLUMNS, GRADE_BANDS
except ImportError:
    from config import MODEL_PATH, FEATURE_COLUMNS, GRADE_BANDS


class ModelService:
    def __init__(self):
        # Load the trained model once at startup
        if not os.path.exists(MODEL_PATH):
            raise FileNotFoundError(f"Model file not found at: {MODEL_PATH}")
        self.model = joblib.load(MODEL_PATH)

    def gpa_to_grade(self, gpa):
        """
        Converts a numeric GPA into a letter grade (A, B, C, D, F)
        and an integer grade class (0 to 4).
        """
        # Clamp gpa between 0.0 and 4.0
        clamped_gpa = max(0.0, min(4.0, float(gpa)))

        if clamped_gpa >= 3.5:
            return "A", 0
        elif clamped_gpa >= 3.0:
            return "B", 1
        elif clamped_gpa >= 2.5:
            return "C", 2
        elif clamped_gpa >= 2.0:
            return "D", 3
        else:
            return "F", 4

    def predict_single(self, input_dict):
        """
        Runs prediction for one student's input features.
        Returns:
            predicted_gpa (float rounded to 2 decimals)
            letter_grade (str: 'A', 'B', etc.)
            range_min (float: mean - 1 std of individual trees)
            range_max (float: mean + 1 std of individual trees)
            dominant_factor (str: name of highest importance feature)
            feature_importances (list of dicts with feature name and relative weight)
        """
        # Ensure features are in the exact required order
        row_values = [float(input_dict[col]) for col in FEATURE_COLUMNS]
        input_df = pd.DataFrame([row_values], columns=FEATURE_COLUMNS)

        # Base prediction
        predicted_gpa = float(self.model.predict(input_df)[0])
        predicted_gpa = max(0.0, min(4.0, predicted_gpa))
        letter_grade, class_id = self.gpa_to_grade(predicted_gpa)

        # Tree-level predictions to calculate confidence range (mean +/- 1 std)
        tree_preds = [float(tree.predict(input_df.values)[0]) for tree in self.model.estimators_]
        std_dev = float(np.std(tree_preds))

        range_min = max(0.0, round(predicted_gpa - std_dev, 2))
        range_max = min(4.0, round(predicted_gpa + std_dev, 2))

        # Overall model feature importances
        raw_importances = self.model.feature_importances_
        feature_importance_list = []
        for col_name, importance in zip(FEATURE_COLUMNS, raw_importances):
            feature_importance_list.append({
                "feature": col_name,
                "importance": round(float(importance), 4),
                "percentage": round(float(importance) * 100, 1),
            })

        # Sort descending by importance
        feature_importance_list.sort(key=lambda x: x["importance"], reverse=True)
        dominant_factor = feature_importance_list[0]["feature"]

        return {
            "predicted_gpa": round(predicted_gpa, 2),
            "letter_grade": letter_grade,
            "grade_class": class_id,
            "range_min": range_min,
            "range_max": range_max,
            "dominant_factor": dominant_factor,
            "feature_importances": feature_importance_list,
        }

    def predict_batch(self, df):
        """
        Runs predictions on a cleaned pandas DataFrame with multiple students.
        Returns the DataFrame with new columns: predicted_gpa and predicted_grade.
        """
        # Select and order required columns
        feature_data = df[FEATURE_COLUMNS]
        raw_predictions = self.model.predict(feature_data)

        # Clip predicted GPAs to 0.0 - 4.0
        predicted_gpas = [round(max(0.0, min(4.0, float(g))), 2) for g in raw_predictions]
        predicted_grades = [self.gpa_to_grade(g)[0] for g in predicted_gpas]

        result_df = df.copy()
        result_df["predicted_gpa"] = predicted_gpas
        result_df["predicted_grade"] = predicted_grades
        return result_df

    def get_global_feature_importances(self):
        """
        Returns the overall model feature importances for charts.
        """
        importances = []
        for name, value in zip(FEATURE_COLUMNS, self.model.feature_importances_):
            importances.append({
                "feature": name,
                "importance": round(float(value), 4),
                "percentage": round(float(value) * 100, 1),
            })
        importances.sort(key=lambda x: x["importance"], reverse=True)
        return importances


# Singleton instance so the model loads only once at application startup
model_service = ModelService()

