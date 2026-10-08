"""Persistence adapters; raw cloud log content lives only in Cloud Storage."""
import os
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


class GCPLogStore:
    def __init__(self, project, bucket, database="log-analyzer", collection="logs",
                 firestore_client=None, storage_client=None):
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
    return GCPLogStore(project, bucket,
                       database=os.environ.get("FIRESTORE_DATABASE", "log-analyzer"),
                       collection=collection)
