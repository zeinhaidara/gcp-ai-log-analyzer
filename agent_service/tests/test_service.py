import base64
import json
import unittest
from unittest.mock import AsyncMock, Mock, patch
from fastapi.testclient import TestClient
from google.api_core.exceptions import Conflict
import service

LOG_ID = "8f99913a-fb03-43d4-9427-9fb9716d236f"


def message(data):
    return {"message": {"data": base64.b64encode(json.dumps(data).encode()).decode()}}


class HandlerTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(service.app)

    def test_health(self):
        self.assertEqual(self.client.get("/health").status_code, 200)

    def test_ack_after_processing(self):
        with patch.object(service, "process", new=AsyncMock()) as process:
            self.assertEqual(self.client.post("/pubsub", json=message({"log_id": LOG_ID})).status_code, 204)
            process.assert_awaited_once_with(LOG_ID)

    def test_failure_is_retried_without_error_details(self):
        with patch.object(service, "process", new=AsyncMock(side_effect=RuntimeError("secret"))):
            response = self.client.post("/pubsub", json=message({"log_id": LOG_ID}))
            self.assertEqual(response.status_code, 503)
            self.assertNotIn("secret", response.text)

    def test_malformed_messages_rejected(self):
        for data in ({}, {"log_id": "../../other"}, {"log_id": 1}, []):
            with patch.object(service, "process", new=AsyncMock()) as process:
                self.assertEqual(self.client.post("/pubsub", json=message(data)).status_code, 400)
                process.assert_not_awaited()
        self.assertEqual(self.client.post("/pubsub", json={"message": {"data": "%%%"}}).status_code, 400)

    def test_payload_limit(self):
        self.assertEqual(self.client.post("/pubsub", content="x" * 16385).status_code, 413)

    def test_analytics_retry_reuses_existing_job(self):
        analytics = Mock()
        analytics.load_table_from_json.side_effect = Conflict("already exists")
        with patch.dict(service.os.environ, {"BIGQUERY_TABLE": "p.d.incidents"}):
            service.export_analytics(analytics, LOG_ID, {"severity": "error", "summary": "test"}, "2026-10-08T00:00:00Z", "test-model")
        analytics.get_job.assert_called_once_with("investigation_" + LOG_ID.replace("-", ""), location="us-central1")
        analytics.get_job.return_value.result.assert_called_once_with(timeout=60)

    def test_completed_delivery_skips_model_and_export(self):
        with patch.object(service, "clients", return_value=(Mock(), Mock(), Mock())), patch.object(service, "claim", return_value={"status": "completed"}), patch.object(service, "investigate", new=AsyncMock()) as model, patch.object(service, "export_analytics") as export:
            import asyncio
            asyncio.run(service.process(LOG_ID))
            model.assert_not_awaited()
            export.assert_not_called()


if __name__ == "__main__":
    unittest.main()
