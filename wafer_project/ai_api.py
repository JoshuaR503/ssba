"""ML analysis API and human decision log, usable locally or in a cloud container."""

import hmac
import json
import os
import sqlite3
from pathlib import Path
from uuid import uuid4

from flask import Flask, jsonify, request

from .ai_predictor import SecomPredictor
from .config import PROJECT_ROOT
from .telemetry import utc_now


def create_ai_app(artifacts: Path, review_database: Path, token: str | None = None) -> Flask:
    predictor = SecomPredictor(artifacts)
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 128 * 1024
    review_database.parent.mkdir(parents=True, exist_ok=True)

    def connection():
        return sqlite3.connect(review_database, timeout=10)

    with connection() as db:
        db.execute("""CREATE TABLE IF NOT EXISTS recommendations (
            id TEXT PRIMARY KEY, created_utc TEXT NOT NULL, payload TEXT NOT NULL,
            status TEXT NOT NULL, reviewer TEXT, reviewed_utc TEXT)""")

    @app.before_request
    def authenticate():
        if request.path != "/health" and token:
            supplied = request.headers.get("Authorization", "")
            if not hmac.compare_digest(supplied.encode("utf-8"), f"Bearer {token}".encode("utf-8")):
                return jsonify(error="Unauthorized"), 401

    @app.get("/health")
    def health():
        return jsonify(status="ready", model_id=predictor.artifact["model_id"],
                       rag_enabled=False, hardware_control=False)

    @app.post("/ai/analyze")
    def analyze():
        if not request.is_json:
            return jsonify(error="Expected application/json"), 415
        try:
            result = predictor.analyze(request.get_json())
        except ValueError as exc:
            return jsonify(error=str(exc)), 400
        identifier = str(uuid4())
        result.update(recommendation_id=identifier, review_status="pending_review", created_utc=utc_now())
        with connection() as db:
            db.execute("INSERT INTO recommendations (id, created_utc, payload, status) VALUES (?, ?, ?, ?)",
                       (identifier, result["created_utc"], json.dumps(result, allow_nan=False), "pending_review"))
        return jsonify(result)

    @app.get("/ai/recommendations/<identifier>")
    def recommendation(identifier):
        with connection() as db:
            row = db.execute("SELECT payload, status, reviewer, reviewed_utc FROM recommendations WHERE id = ?",
                             (identifier,)).fetchone()
        if row is None:
            return jsonify(error="Recommendation not found"), 404
        payload = json.loads(row[0])
        payload.update(review_status=row[1], reviewer=row[2], reviewed_utc=row[3])
        return jsonify(payload)

    @app.post("/ai/recommendations/<identifier>/review")
    def review(identifier):
        if not request.is_json:
            return jsonify(error="Expected application/json"), 415
        payload = request.get_json()
        if not isinstance(payload, dict) or set(payload) != {"decision", "reviewer"}:
            return jsonify(error="Expected decision and reviewer"), 400
        if not isinstance(payload["decision"], str) or payload["decision"] not in {"approve", "reject"} or not isinstance(payload["reviewer"], str) or not payload["reviewer"].strip() or len(payload["reviewer"]) > 200:
            return jsonify(error="decision must be approve/reject with a nonempty reviewer"), 400
        status = "approved" if payload["decision"] == "approve" else "rejected"
        with connection() as db:
            if db.execute("SELECT id FROM recommendations WHERE id = ?", (identifier,)).fetchone() is None:
                return jsonify(error="Recommendation not found"), 404
            changed = db.execute(
                "UPDATE recommendations SET status = ?, reviewer = ?, reviewed_utc = ? WHERE id = ? AND status = 'pending_review'",
                (status, payload["reviewer"].strip(), utc_now(), identifier),
            ).rowcount
            if not changed:
                return jsonify(error="Recommendation has already been reviewed"), 409
        return jsonify(recommendation_id=identifier, review_status=status, hardware_action_executed=False)

    return app


def create_cloud_app() -> Flask:
    token = os.environ.get("AI_API_TOKEN", "")
    if not token:
        raise ValueError("Set AI_API_TOKEN before starting the network-facing cloud service")
    artifacts = Path(os.environ.get("AI_ARTIFACT_DIR", str(PROJECT_ROOT / "data/ai/secom-v1")))
    database = Path(os.environ.get("AI_REVIEW_DATABASE", str(PROJECT_ROOT / "data/ai/reviews.sqlite3")))
    return create_ai_app(artifacts, database, token=token)
