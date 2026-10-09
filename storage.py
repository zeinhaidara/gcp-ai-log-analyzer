"""Persistence adapters; raw cloud log content lives only in Cloud Storage."""
import os
import base64
import json
import logging
import sqlite3
from contextlib import closing
from pathlib import Path

SUMMARY_FIELDS = ("id", "filename", "timestamp", "status", "error_count", "warning_count")


class StorageUnavailable(Exception):
    """The configured persistence service could not complete a request."""


class SQLiteLogStore:
    def __init__(self, database):
        self.database = database
        Path(database).parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(database)) as db, db:
            db.execute("CREATE TABLE IF NOT EXISTS logs (id TEXT PRIMARY KEY, filename TEXT, timestamp TEXT, status TEXT, content TEXT, error_count INTEGER, warning_count INTEGER)")

    def save(self, record):
        try:
            with closing(sqlite3.connect(self.database)) as db, db:
                db.execute("INSERT INTO logs (id, filename, timestamp, status, content, error_count, warning_count) VALUES (?, ?, ?, ?, ?, ?, ?)",
                           tuple(record[field] for field in ("id", "filename", "timestamp", "status", "content", "error_count", "warning_count")))
        except sqlite3.Error as error:
            raise StorageUnavailable() from error

    def list_recent(self):
        try:
            with closing(sqlite3.connect(self.database)) as db:
                db.row_factory = sqlite3.Row
                rows = db.execute("SELECT id, filename, timestamp, status, error_count, warning_count FROM logs ORDER BY timestamp DESC LIMIT 100").fetchall()
                return [dict(row) for row in rows]
        except sqlite3.Error as error:
            raise StorageUnavailable() from error

    def get(self, log_id):
        try:
            with closing(sqlite3.connect(self.database)) as db:
                db.row_factory = sqlite3.Row
                row = db.execute("SELECT * FROM logs WHERE id = ?", (log_id,)).fetchone()
                return dict(row) if row else None
        except sqlite3.Error as error:
            raise StorageUnavailable() from error

    def investigation(self, log_id):
        return {"status": "disabled"} if self.get(log_id) else None

    def enqueue(self, log_id):
        return {"status": "disabled"}


class GCPLogStore:
    def __init__(self, project, bucket, database="(default)", collection="logs",
                 firestore_client=None, storage_client=None, topic=None, publish_client=None):
        # Local SQLite use requires neither Google libraries nor cloud credentials.
        from google.api_core.exceptions import GoogleAPICallError, RetryError
        from google.auth.exceptions import GoogleAuthError
        from google.cloud import firestore, storage
        from google.cloud.storage.exceptions import DataCorruption
        from requests.exceptions import RequestException

        self.cloud_errors = (GoogleAPICallError, RetryError, GoogleAuthError,
                             DataCorruption, RequestException)
        self.firestore = firestore_client if firestore_client is not None else firestore.Client(project=project, database=database)
        self.storage = storage_client if storage_client is not None else storage.Client(project=project)
        self.collection = self.firestore.collection(collection)
        self.bucket = self.storage.bucket(bucket)
        self.topic = topic
        self.project = project
        self.publisher = publish_client
        if topic and self.publisher is None:
            # Reuse attached ADC; synchronous REST keeps publishing bounded without
            # background publisher threads or another application dependency.
            import google.auth
            from google.auth.transport.requests import AuthorizedSession
            credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/pubsub"])
            self.publisher = AuthorizedSession(credentials)

    def enqueue(self, log_id):
        if not self.topic:
            return {"status": "disabled"}
        data = base64.b64encode(json.dumps({"log_id": log_id}).encode()).decode()
        try:
            response = self.publisher.post(
                f"https://pubsub.googleapis.com/v1/projects/{self.project}/topics/{self.topic}:publish",
                json={"messages": [{"data": data}]}, timeout=10)
            response.raise_for_status()
            if not response.json().get("messageIds"):
                raise ValueError("Missing publication receipt")
            self.collection.document(log_id).update({"investigation_dispatch": "queued"}, timeout=10, retry=None)
            return {"status": "queued"}
        except self.cloud_errors + (ValueError,) as error:
            try:
                self.collection.document(log_id).update({"investigation_dispatch": "enqueue_failed"}, timeout=10, retry=None)
            except self.cloud_errors:
                logging.error("Unable to record investigation publication failure")
            raise StorageUnavailable() from error

    def investigation(self, log_id):
        try:
            # Polling reads metadata only, never downloads the raw file again.
            upload = self.collection.document(log_id).get(timeout=10, retry=None)
            if not upload.exists:
                return None
            if not self.topic:
                return {"status": "disabled"}
            document = self.firestore.collection("investigations").document(log_id).get(timeout=10, retry=None)
            if not document.exists:
                metadata = upload.to_dict()
                status = metadata.get("investigation_dispatch", "waiting") if isinstance(metadata, dict) else "waiting"
                result = {"status": status}
                if status == "enqueue_failed":
                    result["error"] = "Upload saved. Retry the investigation without uploading again."
                return result
            data = document.to_dict()
            # Do not expose the worker's lease or internal identity.
            return {key: data[key] for key in ("status", "findings", "model", "completed_at", "truncated", "service_name", "failure_category", "history_count", "history_available") if key in data}
        except self.cloud_errors + (KeyError, TypeError) as error:
            raise StorageUnavailable() from error

    def save(self, record):
        object_name = f"logs/{record['id']}.txt"
        metadata = {field: record[field] for field in SUMMARY_FIELDS}
        metadata["object_name"] = object_name
        try:
            # Publish metadata only after the raw object is durable. Neither write
            # may overwrite existing data. Cloud cross-service writes are not atomic.
            self.bucket.blob(object_name).upload_from_string(
                record["content"].encode("utf-8"), content_type="text/plain; charset=utf-8",
                if_generation_match=0, timeout=10, retry=None)
            self.collection.document(record["id"]).create(metadata, timeout=10, retry=None)
        except self.cloud_errors as error:
            # A timed-out Firestore create may actually have committed. Keep the
            # object so a successful commit can never reference a deleted file.
            raise StorageUnavailable() from error

    def list_recent(self):
        try:
            documents = self.collection.order_by("timestamp", direction="DESCENDING").limit(100).stream(timeout=10, retry=None)
            records = []
            for document in documents:
                metadata = document.to_dict()
                records.append({field: metadata[field] for field in SUMMARY_FIELDS})
            return records
        except self.cloud_errors + (KeyError, TypeError) as error:
            raise StorageUnavailable() from error

    def get(self, log_id):
        try:
            document = self.collection.document(log_id).get(timeout=10, retry=None)
            if not document.exists:
                return None
            metadata = document.to_dict()
            if metadata["object_name"] != f"logs/{log_id}.txt":
                raise ValueError("Unexpected log object name")
            record = {field: metadata[field] for field in SUMMARY_FIELDS}
            record["content"] = self.bucket.blob(metadata["object_name"]).download_as_bytes(timeout=10, retry=None).decode("utf-8")
            return record
        except self.cloud_errors + (UnicodeError, KeyError, TypeError, ValueError) as error:
            raise StorageUnavailable() from error


def create_store(database=None):
    if database is not None:
        return SQLiteLogStore(database)
    backend = os.environ.get("STORAGE_BACKEND", "sqlite").lower()
    if backend == "sqlite":
        if os.environ.get("K_SERVICE"):
            raise ValueError("Cloud Run requires STORAGE_BACKEND=gcp; SQLite is ephemeral there.")
        return SQLiteLogStore(os.environ.get("DATABASE_PATH", "data/logs.db"))
    if backend != "gcp":
        raise ValueError("STORAGE_BACKEND must be sqlite or gcp.")
    project = os.environ.get("GOOGLE_CLOUD_PROJECT")
    bucket = os.environ.get("LOG_BUCKET")
    if not project or not bucket:
        raise ValueError("GCP storage requires GOOGLE_CLOUD_PROJECT and LOG_BUCKET.")
    collection = os.environ.get("FIRESTORE_COLLECTION", "logs")
    if not collection or "/" in collection:
        raise ValueError("FIRESTORE_COLLECTION must be a single collection name.")
    topic = os.environ.get("INVESTIGATION_TOPIC")
    if topic and "/" in topic:
        raise ValueError("INVESTIGATION_TOPIC must be a topic ID.")
    return GCPLogStore(project, bucket,
                       database=os.environ.get("FIRESTORE_DATABASE", "(default)"),
                       collection=collection, topic=topic)
