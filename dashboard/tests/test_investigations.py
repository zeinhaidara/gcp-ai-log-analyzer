import unittest
from unittest.mock import Mock

from investigations import InvestigationNotFound, InvestigationUnavailable, StoreInvestigations
from storage import StorageUnavailable


class InvestigationTests(unittest.TestCase):
    def setUp(self):
        self.store = Mock()
        self.store.investigation.return_value = {"status": "waiting"}
        self.store.enqueue.return_value = {"status": "queued"}
        self.control = StoreInvestigations(self.store)

    def test_queue_publishes_saved_id(self):
        self.assertEqual(self.control.queue("saved-id"), {"status": "queued"})
        self.store.enqueue.assert_called_once_with("saved-id")

    def test_active_or_disabled_investigations_do_not_republish(self):
        for status in ("completed", "processing", "queued", "disabled"):
            self.store.investigation.return_value = {"status": status}
            self.assertEqual(self.control.queue("saved-id")["status"], status)
        self.store.enqueue.assert_not_called()

    def test_missing_log_is_not_published(self):
        self.store.investigation.return_value = None
        with self.assertRaises(InvestigationNotFound):
            self.control.queue("unknown")
        self.store.enqueue.assert_not_called()

    def test_storage_failures_become_unavailable(self):
        self.store.investigation.side_effect = StorageUnavailable()
        with self.assertRaises(InvestigationUnavailable):
            self.control.get("saved-id")
        self.store.investigation.side_effect = None
        self.store.enqueue.side_effect = StorageUnavailable()
        with self.assertRaises(InvestigationUnavailable):
            self.control.queue("saved-id")


if __name__ == "__main__":
    unittest.main()
