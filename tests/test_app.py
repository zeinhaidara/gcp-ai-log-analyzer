import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
from app import create_app
from storage import StorageUnavailable


class AppTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.database = str(Path(self.temp.name) / "logs.db")
        self.app = create_app(self.database)

    def tearDown(self):
        self.temp.cleanup()

    def request(self, path, method="GET", payload=None, raw=None, length=None):
        body = raw if raw is not None else json.dumps(payload).encode() if payload is not None else b""
        statuses = []
        result = self.app({"PATH_INFO": path, "REQUEST_METHOD": method, "CONTENT_LENGTH": str(length if length is not None else len(body)), "wsgi.input": io.BytesIO(body)}, lambda status, headers: statuses.append(status))
        return statuses[0], json.loads(b"".join(result))

    def test_health(self):
        self.assertEqual(self.request("/health"), ("200 OK", {"status": "ok"}))

    def test_upload_list_detail_and_persistence(self):
        status, log = self.request("/logs", "POST", {"filename": "api.txt", "content": "ERROR timeout\nWARN retry\nINFO ready"})
        self.assertEqual(status, "201 Created")
        self.assertEqual((log["error_count"], log["warning_count"]), (1, 1))
        self.app = create_app(self.database)
        self.assertEqual(self.request("/logs")[1][0]["id"], log["id"])
        self.assertNotIn("content", self.request("/logs")[1][0])
        self.assertEqual(self.request("/logs/" + log["id"])[1]["content"], log["content"])

    def test_reject_invalid_uploads(self):
        for payload in [{"filename": "bad.exe", "content": "hello"}, {"filename": "../a.txt", "content": "hello"}, {"filename": "a.txt", "content": " "}, {"filename": "a.txt", "content": 12}, []]:
            with self.subTest(payload=payload):
                self.assertEqual(self.request("/logs", "POST", payload)[0], "400 Bad Request")
        self.assertEqual(self.request("/logs", "POST", raw=b"invalid")[0], "400 Bad Request")
        self.assertEqual(self.request("/logs", "POST", raw=b"\xff")[0], "400 Bad Request")
        self.assertEqual(self.request("/logs", "POST", {"filename": "a.txt", "content": "\ud800"})[0], "400 Bad Request")

    def test_size_limit(self):
        self.assertEqual(self.request("/logs", "POST", raw=b"x", length=1048577)[0], "413 Payload Too Large")

    def test_missing_log(self):
        self.assertEqual(self.request("/logs/missing")[0], "404 Not Found")

    def test_storage_failures_return_safe_503_and_health_stays_available(self):
        store = Mock()
        for operation in (store.save, store.list_recent, store.get):
            operation.side_effect = StorageUnavailable("private content or credentials")
        self.app = create_app(store=store)
        cases = [("/logs", "POST", {"filename": "a.txt", "content": "ERROR test"}),
                 ("/logs", "GET", None),
                 ("/logs/00000000-0000-4000-8000-000000000001", "GET", None)]
        with self.assertLogs("app", level="ERROR") as logs:
            for path, method, payload in cases:
                status, response = self.request(path, method, payload)
                self.assertEqual(status, "503 Service Unavailable")
                self.assertNotIn("private", response["error"])
        self.assertNotIn("private", " ".join(logs.output))
        self.assertEqual(self.request("/health")[0], "200 OK")

    def test_invalid_cloud_document_paths_never_reach_store(self):
        store = Mock()
        self.app = create_app(store=store)
        for path in ("/logs/", "/logs/a/b/c", "/logs/../../secret", "/logs/invalid"):
            self.assertEqual(self.request(path)[0], "404 Not Found")
        store.get.assert_not_called()

    def test_local_upload_explains_ai_is_disabled(self):
        _, log = self.request("/logs", "POST", {"filename": "a.txt", "content": "INFO test"})
        self.assertEqual(log["investigation"]["status"], "disabled")
        self.assertEqual(self.request("/investigations/" + log["id"])[1], {"status": "disabled"})

    def test_publish_failure_keeps_upload_and_retry_reuses_saved_id(self):
        store = Mock()
        store.enqueue.side_effect = [StorageUnavailable("private token"), {"status": "queued"}]
        store.investigation.return_value = {"status": "waiting"}
        self.app = create_app(store=store)
        with self.assertLogs("app", level="ERROR") as logs:
            status, log = self.request("/logs", "POST", {"filename": "a.txt", "content": "ERROR synthetic"})
        self.assertEqual(status, "201 Created")
        self.assertEqual(log["investigation"]["status"], "enqueue_failed")
        self.assertNotIn("private", str(log) + str(logs.output))
        self.assertEqual(self.request("/investigations/" + log["id"], "POST"), ("202 Accepted", {"status": "queued"}))
        store.save.assert_called_once()
        self.assertEqual([call.args[0] for call in store.enqueue.call_args_list], [log["id"], log["id"]])

    def test_completed_processing_and_missing_investigations_do_not_republish(self):
        store = Mock()
        self.app = create_app(store=store)
        path = "/investigations/00000000-0000-4000-8000-000000000001"
        for status in ("completed", "processing", "disabled"):
            store.investigation.return_value = {"status": status}
            self.assertEqual(self.request(path, "POST")[1]["status"], status)
        store.investigation.return_value = None
        self.assertEqual(self.request(path, "POST")[0], "404 Not Found")
        store.enqueue.assert_not_called()

    def test_invalid_investigation_ids_never_reach_cloud(self):
        store = Mock()
        self.app = create_app(store=store)
        for path in ("/investigations/", "/investigations/../../secret", "/investigations/invalid"):
            for method in ("GET", "POST"):
                self.assertEqual(self.request(path, method)[0], "404 Not Found")
        store.investigation.assert_not_called()
        store.enqueue.assert_not_called()


if __name__ == "__main__":
    unittest.main()
