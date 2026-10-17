"""Check the trained model's request contract and non-actuating review workflow."""

import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from wafer_project.ai_api import create_ai_app, create_cloud_app
from wafer_project.ai_predictor import SecomPredictor
from wafer_project.ai_training import read_secom

ROOT = Path(__file__).resolve().parent.parent
ARTIFACTS = ROOT / "data/ai/secom-v1"


class AiIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (ARTIFACTS / "model.joblib").exists():
            raise unittest.SkipTest("Run ai-train to create the trained artifact before AI integration tests")
        cls.payload = json.loads((ARTIFACTS / "demo_input.json").read_text())
        cls.predictor = SecomPredictor(ARTIFACTS)

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.app = create_ai_app(ARTIFACTS, Path(self.temporary.name) / "reviews.sqlite3", token="test-only-token")
        self.client = self.app.test_client()
        self.headers = {"Authorization": "Bearer test-only-token"}

    def test_api_returns_the_actual_pipeline_score_without_retrieval_or_actuation(self):
        offline = self.predictor.analyze(self.payload)
        response = self.client.post("/ai/analyze", json=self.payload, headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertAlmostEqual(response.json["risk_score"], offline["risk_score"])
        self.assertFalse(response.json["rag_enabled"])
        self.assertFalse(response.json["hardware_action_executed"])
        self.assertEqual(response.json["review_status"], "pending_review")
        self.assertEqual(len(response.json["feature_contributions"]), 5)

    def test_authentication_is_required_when_token_is_configured(self):
        self.assertEqual(self.client.get("/health").status_code, 200)
        self.assertEqual(self.client.post("/ai/analyze", json=self.payload).status_code, 401)
        self.assertEqual(self.client.post("/ai/analyze", json=self.payload, headers={"Authorization": "Bearer wrong"}).status_code, 401)

    def test_cloud_factory_requires_explicit_api_authentication(self):
        with patch.dict("os.environ", {"AI_API_TOKEN": ""}):
            with self.assertRaisesRegex(ValueError, "AI_API_TOKEN"):
                create_cloud_app()

    def test_bad_feature_vectors_are_rejected(self):
        for values in ([1, 2], [None] * 590, [True] + [0] * 589, ["invalid"] + [0] * 589):
            with self.subTest(values=values[:2]):
                payload = {"record_id": "bad-input", "features": values}
                self.assertEqual(self.client.post("/ai/analyze", json=payload, headers=self.headers).status_code, 400)

    def test_temperature_is_separate_context_not_a_model_feature(self):
        payload = copy.deepcopy(self.payload)
        payload["context"] = {"cpu_temperature_c": 78, "cpu_temperature_source": "synthetic"}
        hot = self.predictor.analyze(payload)
        payload["context"] = {"cpu_temperature_c": 42, "cpu_temperature_source": "synthetic"}
        cool = self.predictor.analyze(payload)
        self.assertEqual(hot["risk_score"], cool["risk_score"])
        self.assertTrue(hot["cpu_advisories"])
        self.assertFalse(cool["cpu_advisories"])
        self.assertFalse(hot["cpu_temperature_used_by_ml_model"])

    def test_human_review_is_logged_but_never_executes_hardware(self):
        response = self.client.post("/ai/analyze", json=self.payload, headers=self.headers)
        identifier = response.json["recommendation_id"]
        endpoint = f"/ai/recommendations/{identifier}/review"
        malformed = self.client.post(endpoint, json={"decision": [], "reviewer": "test operator"}, headers=self.headers)
        self.assertEqual(malformed.status_code, 400)
        reviewed = self.client.post(endpoint, json={"decision": "approve", "reviewer": "test operator"}, headers=self.headers)
        self.assertEqual(reviewed.status_code, 200)
        self.assertFalse(reviewed.json["hardware_action_executed"])
        self.assertEqual(self.client.post(endpoint, json={"decision": "reject", "reviewer": "another test"}, headers=self.headers).status_code, 409)
        stored = self.client.get(f"/ai/recommendations/{identifier}", headers=self.headers).json
        self.assertEqual(stored["review_status"], "approved")
        self.assertEqual(stored["reviewer"], "test operator")

    def test_chronological_dataset_splits_are_disjoint_and_have_no_label_feature(self):
        frame, _, features = read_secom(ROOT / "data/datasets/secom/uci-secom.csv")
        train, validation, test = [frame[frame.split == name] for name in ("train", "validation", "test")]
        self.assertLess(train.timestamp.max(), validation.timestamp.min())
        self.assertLess(validation.timestamp.max(), test.timestamp.min())
        self.assertEqual(len(features), 590)
        self.assertNotIn("Pass/Fail", features)
        self.assertNotIn("Time", features)
        self.assertTrue(frame.record_id.is_unique)


if __name__ == "__main__":
    unittest.main()
