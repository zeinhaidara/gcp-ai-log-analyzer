import json
import unittest
from unittest.mock import Mock, patch
from investigations import GCPInvestigations, InvestigationNotFound, InvestigationUnavailable


class InvestigationTests(unittest.TestCase):
    def setUp(self):
        self.db, self.publisher = Mock(), Mock()
        self.logs, self.results = Mock(), Mock()
        self.db.collection.side_effect = lambda name: self.logs if name == "logs" else self.results
        self.upload = self.logs.document.return_value.get.return_value
        self.upload.exists = True
        self.upload.to_dict.return_value = {}
        self.result = self.results.document.return_value.get.return_value
        self.result.exists = False
        self.control = GCPInvestigations("project", "topic", "(default)", "logs", self.db, self.publisher)

    def test_publish_uses_saved_id_and_records_queue_state(self):
        self.assertEqual(self.control.queue("saved-id"), {"status": "queued"})
        data = self.publisher.publish.call_args.args[1]
        self.assertEqual(json.loads(data), {"log_id": "saved-id"})
        self.publisher.publish.return_value.result.assert_called_once_with(timeout=10)
        self.logs.document.return_value.update.assert_called_once_with({"investigation_dispatch": "queued"}, timeout=10, retry=None)

    def test_publish_failure_marks_saved_log_for_retry(self):
        self.publisher.publish.return_value.result.side_effect = TimeoutError("private details")
        with self.assertRaises(InvestigationUnavailable):
            self.control.queue("saved-id")
        self.logs.document.return_value.update.assert_called_once_with({"investigation_dispatch": "dispatch_failed"}, timeout=10, retry=None)

    def test_completed_or_queued_requests_do_not_republish(self):
        for status in ("completed", "processing", "queued"):
            with patch.object(self.control, "get", return_value={"status": status}):
                self.assertEqual(self.control.queue("saved-id")["status"], status)
        self.publisher.publish.assert_not_called()

    def test_missing_log_is_not_published(self):
        self.upload.exists = False
        with self.assertRaises(InvestigationNotFound):
            self.control.queue("unknown")
        self.publisher.publish.assert_not_called()

    def test_results_exclude_internal_lease_and_owner(self):
        self.result.exists = True
        self.result.to_dict.return_value = {"status": "completed", "findings": {"summary": "test"}, "owner": "private", "lease_until": "internal"}
        self.assertEqual(self.control.get("saved-id"), {"status": "completed", "findings": {"summary": "test"}})
