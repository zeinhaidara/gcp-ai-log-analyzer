import os
import base64
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from google.api_core.exceptions import NotFound, ServiceUnavailable
from google.cloud import firestore, storage

from storage import GCPLogStore, SQLiteLogStore, StorageUnavailable, create_store


def record(number=1):
    return {"id": f"00000000-0000-4000-8000-{number:012d}", "filename": "api.txt",
            "timestamp": f"2026-10-08T12:00:{number % 60:02d}+00:00",
            "status": "processed", "content": "ERROR café\nWARN retry",
            "error_count": 1, "warning_count": 1}


class GCPStorageTests(unittest.TestCase):
    def setUp(self):
        self.firestore = Mock(spec=firestore.Client)
        self.storage = Mock(spec=storage.Client)
        self.collection = self.firestore.collection.return_value
        self.bucket = self.storage.bucket.return_value
        self.blob = self.bucket.blob.return_value
        self.document = self.collection.document.return_value
        self.store = self.new_store()

    def new_store(self):
        return GCPLogStore("test-project", "test-bucket", firestore_client=self.firestore,
                           storage_client=self.storage)

    def snapshot(self, metadata):
        snapshot = Mock()
        snapshot.exists = True
        snapshot.to_dict.return_value = metadata
        return snapshot

    def test_raw_content_separate_and_readable_by_fresh_store(self):
        log = record()
        self.store.save(log)
        metadata = self.document.create.call_args.args[0]
        self.assertNotIn("content", metadata)
        self.assertEqual(metadata["object_name"], f"logs/{log['id']}.txt")
        self.blob.upload_from_string.assert_called_once_with(
            log["content"].encode("utf-8"), content_type="text/plain; charset=utf-8",
            if_generation_match=0, timeout=10, retry=None)
        self.document.get.return_value = self.snapshot(metadata)
        self.blob.download_as_bytes.return_value = log["content"].encode("utf-8")
        self.assertEqual(self.new_store().get(log["id"]), log)

    def test_list_metadata_only_with_limit_and_order(self):
        metadata = dict(record(), object_name="internal")
        query = self.collection.order_by.return_value.limit.return_value
        query.stream.return_value = [self.snapshot(metadata)]
        result = self.store.list_recent()
        self.collection.order_by.assert_called_once_with("timestamp", direction="DESCENDING")
        self.collection.order_by.return_value.limit.assert_called_once_with(100)
        self.assertNotIn("content", result[0])
        self.assertNotIn("object_name", result[0])
        self.blob.download_as_bytes.assert_not_called()

    def test_failed_upload_does_not_publish_metadata(self):
        self.blob.upload_from_string.side_effect = ServiceUnavailable("private provider error")
        with self.assertRaises(StorageUnavailable):
            self.store.save(record())
        self.document.create.assert_not_called()

    def test_uncertain_metadata_commit_keeps_raw_object(self):
        self.document.create.side_effect = ServiceUnavailable("commit may have succeeded")
        with self.assertRaises(StorageUnavailable):
            self.store.save(record())
        self.blob.upload_from_string.assert_called_once()
        self.blob.delete.assert_not_called()

    def test_missing_document_does_not_read_object(self):
        self.document.get.return_value.exists = False
        self.assertIsNone(self.store.get(record()["id"]))
        self.blob.download_as_bytes.assert_not_called()

    def test_missing_raw_object_is_unavailable_not_missing_log(self):
        log = record()
        self.document.get.return_value = self.snapshot(dict(log, object_name=f"logs/{log['id']}.txt"))
        self.blob.download_as_bytes.side_effect = NotFound("missing object")
        with self.assertRaises(StorageUnavailable):
            self.store.get(log["id"])

    def test_stream_failure_is_reported(self):
        def failing_stream():
            yield self.snapshot(record())
            raise ServiceUnavailable("stream interrupted")
        self.collection.order_by.return_value.limit.return_value.stream.return_value = failing_stream()
        with self.assertRaises(StorageUnavailable):
            self.store.list_recent()

    def test_unexpected_object_reference_is_rejected(self):
        self.document.get.return_value = self.snapshot(dict(record(), object_name="other/private.txt"))
        with self.assertRaises(StorageUnavailable):
            self.store.get(record()["id"])
        self.blob.download_as_bytes.assert_not_called()

    def test_publication_contains_only_log_id_and_waits_for_receipt(self):
        publisher = Mock()
        publisher.post.return_value.json.return_value = {"messageIds": ["123"]}
        store = GCPLogStore("test-project", "test-bucket", firestore_client=self.firestore,
                            storage_client=self.storage, topic="investigations", publish_client=publisher)
        self.assertEqual(store.enqueue(record()["id"]), {"status": "queued"})
        call = publisher.post.call_args
        self.assertEqual(call.args[0], "https://pubsub.googleapis.com/v1/projects/test-project/topics/investigations:publish")
        self.assertEqual(json.loads(base64.b64decode(call.kwargs["json"]["messages"][0]["data"])), {"log_id": record()["id"]})
        self.assertEqual(call.kwargs["timeout"], 10)
        publisher.post.return_value.raise_for_status.assert_called_once()

    def test_publication_timeout_is_recoverable(self):
        from requests.exceptions import Timeout
        publisher = Mock()
        publisher.post.side_effect = Timeout("private token")
        store = GCPLogStore("test-project", "test-bucket", firestore_client=self.firestore,
                            storage_client=self.storage, topic="investigations", publish_client=publisher)
        with self.assertRaises(StorageUnavailable):
            store.enqueue(record()["id"])
        self.document.create.assert_not_called()

    def test_results_read_metadata_only_and_hide_worker_lease(self):
        results = Mock()
        self.firestore.collection.side_effect = lambda name: results if name == "investigations" else self.collection
        self.document.get.return_value.exists = True
        results.document.return_value.get.return_value = self.snapshot(
            {"status": "completed", "findings": {"summary": "Timeout"}, "model": "test",
             "owner": "internal", "lease_until": "internal"})
        store = GCPLogStore("test-project", "test-bucket", firestore_client=self.firestore,
                            storage_client=self.storage, topic="investigations", publish_client=Mock())
        data = store.investigation(record()["id"])
        self.assertEqual(data["status"], "completed")
        self.assertNotIn("owner", data)
        self.assertNotIn("lease_until", data)
        self.blob.download_as_bytes.assert_not_called()
        results.document.return_value.get.return_value.exists = False
        self.assertEqual(store.investigation(record()["id"]), {"status": "waiting"})
        self.document.get.return_value.exists = False
        self.assertIsNone(store.investigation(record()["id"]))


class StorageConfigurationTests(unittest.TestCase):
    def test_cloud_configuration_required(self):
        with patch.dict(os.environ, {"STORAGE_BACKEND": "gcp"}, clear=True):
            with self.assertRaisesRegex(ValueError, "GOOGLE_CLOUD_PROJECT and LOG_BUCKET"):
                create_store()

    def test_unknown_backend_rejected(self):
        with patch.dict(os.environ, {"STORAGE_BACKEND": "typo"}, clear=True):
            with self.assertRaisesRegex(ValueError, "sqlite or gcp"):
                create_store()

    def test_cloud_run_cannot_silently_use_sqlite(self):
        with patch.dict(os.environ, {"K_SERVICE": "log-analyzer"}, clear=True):
            with self.assertRaisesRegex(ValueError, "ephemeral"):
                create_store()

    def test_cloud_configuration_routes_to_named_database(self):
        settings = {"STORAGE_BACKEND": "gcp", "GOOGLE_CLOUD_PROJECT": "test-project",
                    "LOG_BUCKET": "test-bucket"}
        with patch.dict(os.environ, settings, clear=True), patch("storage.GCPLogStore") as store:
            self.assertIs(create_store(), store.return_value)
            store.assert_called_once_with("test-project", "test-bucket", database="(default)", collection="logs", topic=None)

    def test_sqlite_list_limit_and_content_exclusion(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteLogStore(str(Path(directory) / "logs.db"))
            for number in range(101):
                log = record(number)
                log["timestamp"] = f"{number:03d}"
                store.save(log)
            records = store.list_recent()
            self.assertEqual(len(records), 100)
            self.assertEqual(records[0]["id"], record(100)["id"])
            self.assertNotIn("content", records[0])


if __name__ == "__main__":
    unittest.main()
