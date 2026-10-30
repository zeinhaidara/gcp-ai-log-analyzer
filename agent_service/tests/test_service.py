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
        with patch.object(service, "clients", return_value=(db, objects, analytics)), patch.object(service, "claim", return_value={}), patch.object(service, "historical_incidents", side_effect=TimeoutError()), patch.object(service, "cached_diagnosis", return_value=None), patch.object(service, "cache_diagnosis"), patch.object(service, "investigate", new=AsyncMock(return_value=findings)) as model, patch.object(service, "save_if_owned") as save, patch.object(service, "export_analytics") as export, patch.dict(service.os.environ, {"LOG_BUCKET": "test-bucket"}):
            asyncio.run(service.process(LOG_ID))
        model.assert_awaited_once_with("INFO orders started\nERROR database timeout", [])
        self.assertFalse(save.call_args_list[0].args[-1]["history_available"])
        self.assertEqual(save.call_args_list[-1].args[-1]["status"], "completed")
        export.assert_called_once()

    def cache_setup(self):
        """db/objects/analytics mocks wired for one process() run."""
        db, objects, analytics = Mock(), Mock(), Mock()
        blob = objects.bucket.return_value.blob.return_value
        blob.size = 100
        blob.download_as_bytes.return_value = b"INFO orders started\nERROR database timed out"
        return db, objects, analytics

    def test_cache_miss_calls_the_model_and_writes_the_cache(self):
        import asyncio
        db, objects, analytics = self.cache_setup()
        findings = {"severity": "error", "summary": "Timeout", "likely_cause": "Unknown", "recommendations": []}
        with patch.object(service, "clients", return_value=(db, objects, analytics)), patch.object(service, "claim", return_value={}), patch.object(service, "historical_incidents", return_value=[]), patch.object(service, "cached_diagnosis", return_value=None), patch.object(service, "cache_diagnosis") as cache_write, patch.object(service, "investigate", new=AsyncMock(return_value=findings)) as model, patch.object(service, "save_if_owned"), patch.object(service, "export_analytics"), patch.dict(service.os.environ, {"LOG_BUCKET": "test-bucket"}):
            asyncio.run(service.process(LOG_ID))
        model.assert_awaited_once()
        cache_write.assert_called_once()
        self.assertEqual(cache_write.call_args.args[-1], findings)

    def test_cache_hit_returns_cached_findings_and_skips_the_model(self):
        import asyncio
        db, objects, analytics = self.cache_setup()
        cached = {"severity": "error", "summary": "Cached", "likely_cause": "Known", "recommendations": []}
        captured = {}
        def save_if_owned(transaction, ref, owner, values):
            captured.update(values)
        with patch.object(service, "clients", return_value=(db, objects, analytics)), patch.object(service, "claim", return_value={}), patch.object(service, "historical_incidents", return_value=[]), patch.object(service, "cached_diagnosis", return_value=cached), patch.object(service, "cache_diagnosis") as cache_write, patch.object(service, "investigate", new=AsyncMock()) as model, patch.object(service, "save_if_owned", side_effect=save_if_owned), patch.object(service, "export_analytics"), patch.dict(service.os.environ, {"LOG_BUCKET": "test-bucket"}):
            asyncio.run(service.process(LOG_ID))
        model.assert_not_awaited()
        cache_write.assert_not_called()
        self.assertEqual(captured["findings"], cached)

    def test_expired_cache_entry_is_treated_as_a_miss(self):
        from datetime import datetime, timedelta, timezone
        db = Mock()
        doc = Mock(exists=True)
        doc.to_dict.return_value = {"findings": {"severity": "error"}, "expires_at": datetime.now(timezone.utc) - timedelta(seconds=1)}
        db.collection.return_value.document.return_value.get.return_value = doc
        self.assertIsNone(service.cached_diagnosis(db, "a-key"))

    def test_cache_key_changes_with_model_or_prompt_version(self):
        with patch.object(service, "MODEL", "model-a"), patch.object(service, "PROMPT_VERSION", "1"):
            base = service.diagnosis_cache_key("same log")
        with patch.object(service, "MODEL", "model-b"), patch.object(service, "PROMPT_VERSION", "1"):
            different_model = service.diagnosis_cache_key("same log")
        with patch.object(service, "MODEL", "model-a"), patch.object(service, "PROMPT_VERSION", "2"):
            different_version = service.diagnosis_cache_key("same log")
        self.assertNotEqual(base, different_model)
        self.assertNotEqual(base, different_version)
        self.assertNotEqual(different_model, different_version)

    def test_failed_or_invalid_model_output_is_not_cached(self):
        import asyncio
        db, objects, analytics = self.cache_setup()
        with patch.object(service, "clients", return_value=(db, objects, analytics)), patch.object(service, "claim", return_value={}), patch.object(service, "historical_incidents", return_value=[]), patch.object(service, "cached_diagnosis", return_value=None), patch.object(service, "cache_diagnosis") as cache_write, patch.object(service, "investigate", new=AsyncMock(side_effect=RuntimeError("no structured findings"))), patch.object(service, "save_if_owned"), patch.object(service, "export_analytics"), patch.dict(service.os.environ, {"LOG_BUCKET": "test-bucket"}):
            with self.assertRaises(RuntimeError):
                asyncio.run(service.process(LOG_ID))
        cache_write.assert_not_called()

    def test_non_empty_history_bypasses_the_cache(self):
        import asyncio
        db, objects, analytics = self.cache_setup()
        findings = {"severity": "error", "summary": "Timeout", "likely_cause": "Unknown", "recommendations": []}
        with patch.object(service, "clients", return_value=(db, objects, analytics)), patch.object(service, "claim", return_value={}), patch.object(service, "historical_incidents", return_value=[{"log_id": "prior", "severity": "error", "summary": "x"}]), patch.object(service, "cached_diagnosis") as cache_read, patch.object(service, "cache_diagnosis") as cache_write, patch.object(service, "investigate", new=AsyncMock(return_value=findings)) as model, patch.object(service, "save_if_owned"), patch.object(service, "export_analytics"), patch.dict(service.os.environ, {"LOG_BUCKET": "test-bucket"}):
            asyncio.run(service.process(LOG_ID))
        cache_read.assert_not_called()
        cache_write.assert_not_called()
        model.assert_awaited_once()

    def test_cache_read_failure_still_runs_the_model_and_saves_findings(self):
        import asyncio
        db, objects, analytics = self.cache_setup()
        findings = {"severity": "error", "summary": "Timeout", "likely_cause": "Unknown", "recommendations": []}
        captured = {}
        def save_if_owned(transaction, ref, owner, values):
            captured.update(values)
        with patch.object(service, "clients", return_value=(db, objects, analytics)), patch.object(service, "claim", return_value={}), patch.object(service, "historical_incidents", return_value=[]), patch.object(service, "cached_diagnosis", side_effect=RuntimeError("secret ai-log-analyzer-511017 credentials")), patch.object(service, "cache_diagnosis"), patch.object(service, "investigate", new=AsyncMock(return_value=findings)) as model, patch.object(service, "save_if_owned", side_effect=save_if_owned), patch.object(service, "export_analytics"), patch.dict(service.os.environ, {"LOG_BUCKET": "test-bucket"}):
            asyncio.run(service.process(LOG_ID))
        model.assert_awaited_once()
        self.assertEqual(captured["findings"], findings)

    def test_cache_write_failure_still_completes_the_investigation(self):
        import asyncio
        db, objects, analytics = self.cache_setup()
        findings = {"severity": "error", "summary": "Timeout", "likely_cause": "Unknown", "recommendations": []}
        statuses = []
        def save_if_owned(transaction, ref, owner, values):
            if "status" in values:
                statuses.append(values["status"])
        with patch.object(service, "clients", return_value=(db, objects, analytics)), patch.object(service, "claim", return_value={}), patch.object(service, "historical_incidents", return_value=[]), patch.object(service, "cached_diagnosis", return_value=None), patch.object(service, "cache_diagnosis", side_effect=RuntimeError("secret ai-log-analyzer-511017 credentials")), patch.object(service, "investigate", new=AsyncMock(return_value=findings)), patch.object(service, "save_if_owned", side_effect=save_if_owned), patch.object(service, "export_analytics"), patch.dict(service.os.environ, {"LOG_BUCKET": "test-bucket"}):
            asyncio.run(service.process(LOG_ID))
        self.assertEqual(statuses[-1], "completed")

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

    def test_health_makes_no_client_calls(self):
        with patch.object(service, "clients") as clients:
            self.assertEqual(self.client.get("/health").status_code, 200)
        clients.assert_not_called()

    def ready(self, db=None, objects=None, analytics=None):
        trio = service.Clients(db or Mock(), objects or Mock(), analytics or Mock())
        env = {"LOG_BUCKET": "test-bucket", "BIGQUERY_TABLE": "p.d.incidents"}
        with patch.object(service, "clients", return_value=trio), patch.dict(service.os.environ, env):
            return self.client.get("/ready"), trio

    def test_ready_when_all_checks_pass(self):
        response, (db, objects, analytics) = self.ready()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ready", "checks": {"firestore": "ok", "storage": "ok", "bigquery": "ok"}})
        objects.bucket.assert_called_once_with("test-bucket")
        objects.bucket.return_value.reload.assert_called_once()
        objects.bucket.return_value.list_blobs.assert_not_called()
        analytics.get_table.assert_called_once()
        analytics.query.assert_not_called()

    def test_ready_reports_one_failure_without_exception_text(self):
        analytics = Mock()
        analytics.get_table.side_effect = RuntimeError("secret ai-log-analyzer-511017 credentials")
        response, _ = self.ready(analytics=analytics)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"status": "not_ready", "checks": {"firestore": "ok", "storage": "ok", "bigquery": "failed"}})
        self.assertNotIn("secret", response.text)
        self.assertNotIn("511017", response.text)

    def test_ready_times_out_slow_check(self):
        import time
        objects = Mock()
        objects.bucket.return_value.reload.side_effect = lambda **kwargs: time.sleep(0.5)
        with patch.object(service, "READY_TIMEOUT", 0.05):
            response, _ = self.ready(objects=objects)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["checks"], {"firestore": "ok", "storage": "failed", "bigquery": "ok"})

    def test_ready_fails_when_configuration_is_missing(self):
        with patch.object(service, "clients", return_value=service.Clients(Mock(), Mock(), Mock())), patch.dict(service.os.environ, {}, clear=True):
            response = self.client.get("/ready")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["checks"]["storage"], "failed")

    def test_clients_are_built_once_across_threads(self):
        import threading
        import time
        def slow(**kwargs):
            time.sleep(0.05)
            return Mock()
        with patch.object(service, "_clients", None), patch.dict(service.os.environ, {"GOOGLE_CLOUD_PROJECT": "p"}), \
                patch.object(service.firestore, "Client", side_effect=slow) as db, \
                patch.object(service.storage, "Client", side_effect=slow) as objects, \
                patch.object(service.bigquery, "Client", side_effect=slow) as analytics:
            results = []
            threads = [threading.Thread(target=lambda: results.append(service.clients())) for _ in range(8)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
        self.assertEqual(len(results), 8)
        self.assertTrue(all(result is results[0] for result in results))
        self.assertEqual((db.call_count, objects.call_count, analytics.call_count), (1, 1, 1))
        self.assertIsInstance(results[0], service.Clients)

    def test_client_build_failure_is_retried(self):
        with patch.object(service, "_clients", None), patch.dict(service.os.environ, {}, clear=True):
            with self.assertRaises(KeyError):
                service.clients()
            with patch.dict(service.os.environ, {"GOOGLE_CLOUD_PROJECT": "p"}), \
                    patch.object(service.firestore, "Client"), patch.object(service.storage, "Client"), \
                    patch.object(service.bigquery, "Client"):
                self.assertIsInstance(service.clients(), service.Clients)

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
