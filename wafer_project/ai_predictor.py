"""Saved ML pipeline inference and numerical explanations. No document retrieval."""

import hashlib
import importlib.metadata
import json
import math
from pathlib import Path

import joblib
import numpy as np
import pandas as pd


class SecomPredictor:
    def __init__(self, artifacts: Path):
        self.metadata = json.loads((artifacts / "model_metadata.json").read_text())
        if self.metadata["packages"]["scikit-learn"] != importlib.metadata.version("scikit-learn"):
            raise ValueError("Model and runtime scikit-learn versions differ; use the pinned AI requirements")
        model_path = artifacts / "model.joblib"
        if hashlib.sha256(model_path.read_bytes()).hexdigest() != self.metadata["model_sha256"]:
            raise ValueError("Model checksum does not match its metadata")
        # Only load this project's locally trained artifact, never an uploaded pickle.
        self.artifact = joblib.load(model_path)

    def analyze(self, payload: object) -> dict:
        if not isinstance(payload, dict) or set(payload) - {"record_id", "features", "context"}:
            raise ValueError("Expected record_id, features and optional context")
        record_id, values = payload.get("record_id"), payload.get("features")
        if not isinstance(record_id, str) or not record_id.strip() or len(record_id) > 200:
            raise ValueError("record_id must be a nonempty string of at most 200 characters")
        if not isinstance(values, list) or len(values) != len(self.artifact["feature_names"]):
            raise ValueError("features must contain the 590 SECOM measurements in column order 0..589")
        for value in values:
            if value is not None and (
                isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)
            ):
                raise ValueError("Features must be finite numbers or null for missing measurements")
        if all(value is None for value in values):
            raise ValueError("At least one measurement is required; all-null inference is not useful")
        context = payload.get("context", {})
        if not isinstance(context, dict) or set(context) - {
            "cpu_temperature_c", "cpu_temperature_source", "lot_id", "queue_length"
        }:
            raise ValueError("Unknown or invalid context fields")
        temperature = context.get("cpu_temperature_c")
        if temperature is not None:
            if (isinstance(temperature, bool) or not isinstance(temperature, (int, float))
                    or not math.isfinite(temperature) or not 0 <= temperature <= 150):
                raise ValueError("CPU temperature must be a finite number between 0 and 150")
            if context.get("cpu_temperature_source") not in {"synthetic", "real_sensor"}:
                raise ValueError("CPU temperature requires source synthetic or real_sensor")
        if "lot_id" in context and (not isinstance(context["lot_id"], str) or len(context["lot_id"]) > 200):
            raise ValueError("lot_id must be a string of at most 200 characters")
        if "queue_length" in context and (type(context["queue_length"]) is not int or context["queue_length"] < 0):
            raise ValueError("queue_length must be a nonnegative integer")
        features = pd.DataFrame([[np.nan if value is None else value for value in values]],
                                columns=self.artifact["feature_names"])
        pipeline = self.artifact["pipeline"]
        score = float(pipeline.predict_proba(features)[0, 1])
        threshold = self.artifact["threshold"]
        transformed = pipeline[:-1].transform(features)[0]
        contributions = transformed * pipeline.named_steps["classifier"].coef_[0]
        indexes = np.argsort(np.abs(contributions))[::-1][:5]
        drivers = [
            {"anonymous_feature": self.artifact["selected_feature_names"][int(index)],
             "failure_log_odds_contribution": float(contributions[index]),
             "direction": "increases_score" if contributions[index] >= 0 else "decreases_score"}
            for index in indexes
        ]
        alert = score >= threshold
        advisory = []
        if temperature is not None and temperature >= 75:
            advisory.append("CPU temperature exceeds the separate 75°C advisory; inspect cooling before approving changes")
        return {
            "record_id": record_id.strip(), "model_id": self.artifact["model_id"],
            "model_kind": "trained logistic regression", "scope": self.metadata["scope"],
            "risk_score": score, "alert_threshold": threshold, "quality_alert": bool(alert),
            "score_is_calibrated_probability": False,
            "recommendation": "operator_inspection" if alert else "monitor_only",
            "explanation": (
                "The learned model score exceeds the validation-selected threshold; review the process record"
                if alert else "The learned model score is below the alert threshold; continue observing the record"
            ),
            "feature_contributions": drivers,
            "contributions_are_causal": False,
            "missing_measurement_fraction": values.count(None) / len(values),
            "context": context, "cpu_advisories": advisory,
            "cpu_temperature_used_by_ml_model": False,
            "human_review_required": True, "hardware_action_executed": False,
            "rag_enabled": False,
        }
