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
    def test_model_receives_numbered_bounded_source_in_one_call(self):
        import asyncio
        from types import SimpleNamespace
        findings = {"severity": "error", "summary": "Timeout", "likely_cause": "Tentative", "recommendations": [], "hypotheses": [{"title": "Candidate", "explanation": "Tentative", "evidence_lines": [1]}]}
        runner = Mock()
        captured = {}
        async def events(**kwargs):
            captured.update(kwargs)
            yield SimpleNamespace(is_final_response=lambda: True, content=SimpleNamespace(parts=[SimpleNamespace(text=json.dumps(findings))]))
        runner.run_async = events
        sessions = Mock()
        sessions.create_session = AsyncMock(return_value=SimpleNamespace(id="test-session"))
        with patch.object(service, "LlmAgent"), patch.object(service, "Runner", return_value=runner), patch.object(service, "InMemorySessionService", return_value=sessions):
            result = asyncio.run(service.investigate("ERROR " + "x" * service.MAX_MODEL_CHARS + "\nUNSEEN_TAIL", []))
        payload = json.loads(captured["new_message"].parts[0].text)
        self.assertTrue(payload["current_log"].startswith("[L1] ERROR"))
        self.assertNotIn("UNSEEN_TAIL", payload["current_log"])
        self.assertEqual(captured["run_config"].max_llm_calls, 1)
        self.assertEqual(result["hypotheses"][0]["evidence_lines"], [1])

    def test_hypothesis_citations_are_bounded_to_supplied_nonempty_log_lines(self):
        findings = {"severity": "error", "summary": "Timeout", "likely_cause": "Tentative", "recommendations": [], "hypotheses": [{"title": "Pool", "explanation": "Candidate", "evidence_lines": [1, 2, 3, 999]}, {"title": "Unsupported", "explanation": "Candidate", "evidence_lines": [999]}]}
        result = service.grounded_findings(json.dumps(findings), "INFO started\n\nERROR timeout")
        self.assertEqual(len(result["hypotheses"]), 1)
        self.assertEqual(result["hypotheses"][0]["evidence_lines"], [1, 3])

    def test_legacy_findings_remain_valid_and_citations_cannot_reach_unseen_tail(self):
        findings = {"severity": "error", "summary": "Timeout", "likely_cause": "Tentative", "recommendations": []}
        self.assertEqual(service.grounded_findings(json.dumps(findings), "ERROR timeout")["hypotheses"], [])
        findings["hypotheses"] = [{"title": "Tail", "explanation": "Not supplied", "evidence_lines": [2]}]
        self.assertEqual(service.grounded_findings(json.dumps(findings), "x" * service.MAX_MODEL_CHARS + "\nERROR tail")["hypotheses"], [])

    def test_classification(self):
        self.assertEqual(service.classify_log("INFO orders started\nERROR database timed out"), ("orders", "database_timeout"))
        self.assertEqual(service.classify_log("ERROR expired_token 401"), ("unknown", "authentication"))
        self.assertEqual(service.classify_log("INFO checkout started\nERROR payment timeout"), ("checkout", "payment_timeout"))

    def test_history_failure_still_completes_investigation(self):
        import asyncio
        db, objects, analytics = Mock(), Mock(), Mock()
        blob = objects.bucket.return_value.blob.return_value
        blob.size = 100
        blob.download_as_bytes.return_value = b"INFO orders started\nERROR database timeout"
        findings = {"severity": "error", "summary": "Timeout", "likely_cause": "Unknown", "recommendations": []}
        with patch.object(service, "clients", return_value=(db, objects, analytics)), patch.object(service, "claim", return_value={}), patch.object(service, "historical_incidents", side_effect=TimeoutError()), patch.object(service, "investigate", new=AsyncMock(return_value=findings)) as model, patch.object(service, "save_if_owned") as save, patch.object(service, "export_analytics") as export, patch.dict(service.os.environ, {"LOG_BUCKET": "test-bucket"}):
            asyncio.run(service.process(LOG_ID))
        model.assert_awaited_once_with("INFO orders started\nERROR database timeout", [])
        self.assertFalse(save.call_args_list[0].args[-1]["history_available"])
        self.assertEqual(save.call_args_list[-1].args[-1]["status"], "completed")
        export.assert_called_once()

    def test_history_query_is_parameterized_bounded_and_truncated(self):
        from types import SimpleNamespace
        analytics = Mock()
        analytics.query.return_value.result.return_value = [SimpleNamespace(log_id="prior", severity="error", summary="x" * 3000)]
        with patch.dict(service.os.environ, {"BIGQUERY_TABLE": "test-project.demo.incidents"}):
            result = service.historical_incidents(analytics, LOG_ID, "orders", "database_timeout")
        self.assertEqual(len(result[0]["summary"]), 2000)
        query = analytics.query.call_args.args[0]
        self.assertIn("log_id != @log_id", query)
        self.assertIn("INTERVAL 7 DAY", query)
        self.assertIn("LIMIT 5", query)
        config = analytics.query.call_args.kwargs["job_config"]
        self.assertEqual(config.maximum_bytes_billed, 52428800)
        self.assertEqual(config.query_parameters[1].value, "orders")

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
