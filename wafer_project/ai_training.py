"""Train a real SECOM quality classifier. No RAG or robot-control code is used."""

import hashlib
import importlib.metadata
import json
import warnings
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.dummy import DummyClassifier
from sklearn.feature_selection import SelectKBest, VarianceThreshold, f_classif
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score, average_precision_score, balanced_accuracy_score,
    confusion_matrix, fbeta_score, precision_recall_curve, precision_score,
    recall_score, roc_auc_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

KAGGLE_PAGE = "https://www.kaggle.com/datasets/paresh2047/uci-semcom"
ORIGINAL_PAGE = "https://archive.ics.uci.edu/dataset/179/secom"


def read_secom(path: Path) -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
    frame = pd.read_csv(path).copy()
    features = [str(index) for index in range(590)]
    if not {"Time", "Pass/Fail", *features}.issubset(frame.columns):
        raise ValueError("Expected the Kaggle SECOM CSV: Time, columns 0..589 and Pass/Fail")
    frame["record_id"] = [f"SECOM_{index:04d}" for index in range(len(frame))]
    frame["timestamp"] = pd.to_datetime(frame["Time"], errors="raise")
    if frame["timestamp"].isna().any() or not frame["Pass/Fail"].isin([-1, 1]).all():
        raise ValueError("SECOM contains invalid timestamps or labels")
    numeric = frame[features].apply(pd.to_numeric, errors="raise")
    if np.isinf(numeric.to_numpy()).any():
        raise ValueError("SECOM contains infinite feature values")
    frame = pd.concat([frame.drop(columns=features), numeric], axis=1).copy()
    frame["failed"] = (frame["Pass/Fail"] == 1).astype(int)
    frame = frame.sort_values(["timestamp", "record_id"]).reset_index(drop=True)
    # Keep identical timestamps together so boundaries do not split a timestamp group.
    train_end, validation_end = int(len(frame) * 0.6), int(len(frame) * 0.8)
    while train_end < len(frame) and frame.iloc[train_end].timestamp == frame.iloc[train_end - 1].timestamp:
        train_end += 1
    while validation_end < len(frame) and frame.iloc[validation_end].timestamp == frame.iloc[validation_end - 1].timestamp:
        validation_end += 1
    frame["split"] = ["train" if index < train_end else "validation" if index < validation_end else "test"
                      for index in range(len(frame))]
    for name in ("train", "validation", "test"):
        subset = frame[frame.split == name]
        if len(subset) < 10 or subset.failed.nunique() != 2:
            raise ValueError("Each chronological split must contain pass and fail examples")
    return frame, frame[["record_id", "Time", "failed", "split"]], features


def build_pipeline(c: float, features_to_select: int = 40) -> Pipeline:
    return Pipeline([
        ("impute", SimpleImputer(strategy="median", add_indicator=True, keep_empty_features=True)),
        ("remove_constants", VarianceThreshold()),
        ("select", SelectKBest(f_classif, k=features_to_select)),
        ("scale", StandardScaler()),
        ("classifier", LogisticRegression(C=c, class_weight="balanced", max_iter=2000, random_state=42)),
    ])


def select_threshold(y: np.ndarray, scores: np.ndarray) -> float:
    precision, recall, thresholds = precision_recall_curve(y, scores)
    denominator = 4 * precision[:-1] + recall[:-1]
    f2 = np.divide(5 * precision[:-1] * recall[:-1], denominator,
                   out=np.zeros_like(denominator), where=denominator > 0)
    # Prefer greater precision when validation F2 ties.
    best = max(range(len(thresholds)), key=lambda index: (f2[index], precision[index], thresholds[index]))
    return float(thresholds[best])


def classification_metrics(y: np.ndarray, scores: np.ndarray, threshold: float) -> dict:
    predicted = (scores >= threshold).astype(int)
    tn, fp, fn, tp = confusion_matrix(y, predicted, labels=[0, 1]).ravel()
    return {
        "samples": len(y), "failures": int(y.sum()), "threshold": float(threshold),
        "accuracy": float(accuracy_score(y, predicted)),
        "balanced_accuracy": float(balanced_accuracy_score(y, predicted)),
        "failure_precision": float(precision_score(y, predicted, zero_division=0)),
        "failure_recall": float(recall_score(y, predicted, zero_division=0)),
        "failure_f2": float(fbeta_score(y, predicted, beta=2, zero_division=0)),
        "average_precision": float(average_precision_score(y, scores)),
        "roc_auc": float(roc_auc_score(y, scores)),
        "confusion_matrix": {"true_negative": int(tn), "false_positive": int(fp),
                             "false_negative": int(fn), "true_positive": int(tp)},
    }


def train_secom(dataset_path: Path, output: Path) -> dict:
    if output.exists() and any(output.iterdir()):
        raise ValueError("Choose a new output directory; an existing model will not be overwritten")
    frame, split_table, features = read_secom(dataset_path)
    train, validation, test = [frame[frame.split == name] for name in ("train", "validation", "test")]
    candidates = []
    fitted_models = []
    for c in (0.01, 0.1, 1.0):
        pipeline = build_pipeline(c)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            pipeline.fit(train[features], train.failed)
        scores = pipeline.predict_proba(validation[features])[:, 1]
        candidates.append({"C": c, "validation_average_precision": float(average_precision_score(validation.failed, scores)),
                           "training_warnings": sorted({str(item.message) for item in caught})})
        fitted_models.append(pipeline)
    best_index = max(range(len(candidates)), key=lambda index: candidates[index]["validation_average_precision"])
    model = fitted_models[best_index]
    threshold = select_threshold(validation.failed.to_numpy(), model.predict_proba(validation[features])[:, 1])
    test_scores = model.predict_proba(test[features])[:, 1]
    dummy = DummyClassifier(strategy="prior").fit(train[features], train.failed)
    baseline_scores = dummy.predict_proba(test[features])[:, 1]
    selected = model.named_steps["impute"].get_feature_names_out(features)
    selected = selected[model.named_steps["remove_constants"].get_support()]
    selected = selected[model.named_steps["select"].get_support()].tolist()
    output.mkdir(parents=True, exist_ok=True)
    model_id = "secom-logistic-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    artifact = {"pipeline": model, "feature_names": features, "selected_feature_names": selected,
                "threshold": threshold, "model_id": model_id}
    joblib.dump(artifact, output / "model.joblib")
    metrics = {
        "model": classification_metrics(test.failed.to_numpy(), test_scores, threshold),
        "always_pass_baseline": classification_metrics(test.failed.to_numpy(), baseline_scores, 0.5),
    }
    metadata = {
        "model_id": model_id, "model_kind": "supervised logistic regression",
        "rag_enabled": False, "training_execution": "local_mac", "cloud_deployed": False,
        "scope": "SECOM semiconductor process-quality classification",
        "source": "real_public_dataset", "kaggle_dataset": "paresh2047/uci-semcom",
        "kaggle_page": KAGGLE_PAGE, "original_source": ORIGINAL_PAGE,
        "original_citation": "McCann, M. & Johnston, A. (2008). SECOM. DOI: 10.24432/C54305.",
        "original_license": "CC BY 4.0 (UCI original source)",
        "dataset_sha256": hashlib.sha256(dataset_path.read_bytes()).hexdigest(),
        "model_sha256": hashlib.sha256((output / "model.joblib").read_bytes()).hexdigest(),
        "feature_count": len(features), "selected_feature_names": selected,
        "split_method": "chronological 60/20/20 with identical timestamps kept together",
        "split_counts": frame.split.value_counts().to_dict(),
        "failure_counts": frame.groupby("split").failed.sum().to_dict(),
        "test_start": test.Time.iloc[0], "test_end": test.Time.iloc[-1],
        "candidate_selection": "validation average precision; test set not used for selection",
        "threshold_selection": "validation F2, then precision to break ties",
        "candidates": candidates, "chosen_C": candidates[best_index]["C"], "threshold": threshold,
        "test_metrics": metrics,
        "packages": {name: importlib.metadata.version(name) for name in ("scikit-learn", "numpy", "pandas", "joblib")},
        "limitations": [
            "Small, imbalanced historical dataset; results may not transfer to modern fabs.",
            "No lot identifiers available for an independent lot-group evaluation.",
            "Anonymous process features are not Pi sensors or CPU temperatures.",
            "Class-weighted model scores are not calibrated failure probabilities.",
            "Predictions do not demonstrate improved robot routing or throughput.",
            "Feature contributions describe model associations, not causal process explanations.",
        ],
    }
    (output / "model_metadata.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    split_table.to_csv(output / "data_splits.csv", index=False)
    predictions = test[["record_id", "Time", "failed"]].copy()
    predictions["risk_score"] = test_scores
    predictions["quality_alert"] = test_scores >= threshold
    predictions.to_csv(output / "heldout_predictions.csv", index=False)
    # Save genuine held-out feature records for an HTTP demonstration, excluding their labels.
    alerts = np.flatnonzero(test_scores >= threshold)
    chosen = int(alerts[0]) if len(alerts) else 0
    record = test.iloc[chosen]
    sample = {
        "record_id": record.record_id,
        "features": [None if pd.isna(value) else float(value) for value in record[features]],
        "context": {"cpu_temperature_c": 48.0, "cpu_temperature_source": "synthetic",
                    "lot_id": "DEMO_ASSOCIATION_ONLY", "queue_length": 3},
    }
    (output / "demo_input.json").write_text(json.dumps(sample, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    lines = ["# SECOM AI evaluation", "",
             "A supervised model trained on the real Kaggle SECOM CSV. Training and evaluation ran locally; RAG is absent.",
             f"Dataset: [{metadata['kaggle_dataset']}]({KAGGLE_PAGE}); [original source]({ORIGINAL_PAGE}).", "",
             f"Chronological split counts: {metadata['split_counts']}. Failure counts: {metadata['failure_counts']}.",
             "Imputation, constant removal, feature selection and scaling were fitted on training data only.",
             "Model strength and alert threshold were selected on validation data; the final test set was evaluated afterward.", "",
             "| Held-out metric | Trained model | Always-pass baseline |", "| --- | ---: | ---: |"]
    for field in ("failure_precision", "failure_recall", "failure_f2", "average_precision", "roc_auc", "balanced_accuracy", "accuracy"):
        lines.append(f"| {field} | {metrics['model'][field]:.4f} | {metrics['always_pass_baseline'][field]:.4f} |")
    lines += ["", f"Model confusion matrix: {metrics['model']['confusion_matrix']}.",
              f"Validation-selected alert threshold: {threshold:.6f}.", "", "## Interpretation", "",
              "An alert requests human review of the process record. It does not authorize a transfer or change a process setting.",
              "The demo's feature vector is a genuine held-out record. Its CPU temperature and lot association are explicitly synthetic context.",
              "The explanation text is generated by application templates from model outputs and numerical contributions, not by an LLM or RAG.", ""]
    lines += [f"- {limitation}" for limitation in metadata["limitations"]]
    (output / "evaluation.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"model_id": model_id, "output": str(output.resolve()), "split_counts": metadata["split_counts"], "test_metrics": metrics}
