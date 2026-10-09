"""Queue investigations after durable uploads and expose safe result fields."""
import os
import json
import logging


class InvestigationUnavailable(Exception):
    pass


class InvestigationNotFound(Exception):
    pass


class LocalInvestigations:
    def __init__(self, store):
        self.store = store

    def queue(self, log_id):
        if self.store.get(log_id) is None:
            raise InvestigationNotFound()
        return {"status": "disabled", "message": "AI investigations require the cloud deployment."}

    def get(self, log_id):
        return self.queue(log_id)


class GCPInvestigations:
    def __init__(self, project, topic, database, collection, db=None, publisher=None):
        from google.cloud import firestore, pubsub_v1
        self.db = db if db is not None else firestore.Client(project=project, database=database)
        self.publisher = publisher if publisher is not None else pubsub_v1.PublisherClient()
        self.topic = self.publisher.topic_path(project, topic)
        self.logs = self.db.collection(collection)

    def get(self, log_id):
        try:
            upload = self.logs.document(log_id).get(timeout=10, retry=None)
            if not upload.exists:
                raise InvestigationNotFound()
            result = self.db.collection("investigations").document(log_id).get(timeout=10, retry=None)
            if not result.exists:
                return {"status": (upload.to_dict() or {}).get("investigation_dispatch", "not_requested")}
            values = result.to_dict() or {}
            return {key: values[key] for key in (
                "status", "findings", "model", "completed_at", "truncated",
                "service_name", "failure_category", "history_count", "history_available") if key in values}
        except InvestigationNotFound:
            raise
        except Exception as exc:
            raise InvestigationUnavailable() from exc

    def queue(self, log_id):
        current = self.get(log_id)
        if current.get("status") in ("completed", "processing", "queued"):
            return current
        try:
            self.publisher.publish(self.topic, json.dumps({"log_id": log_id}).encode()).result(timeout=10)
            self.logs.document(log_id).update({"investigation_dispatch": "queued"}, timeout=10, retry=None)
            return {"status": "queued"}
        except Exception as exc:
            # Publishing may have succeeded despite a timeout. Reusing the UUID lets
            # the agent's lease/completion checks suppress normal duplicate delivery.
            try:
                self.logs.document(log_id).update({"investigation_dispatch": "dispatch_failed"}, timeout=10, retry=None)
            except Exception:
                logging.error("Unable to record investigation dispatch failure")
            raise InvestigationUnavailable() from exc


class StoreInvestigations:
    """Adapt dev's storage API to the feature branch's result routes."""
    def __init__(self, store):
        self.store = store

    def get(self, log_id):
        from storage import StorageUnavailable
        try:
            result = self.store.investigation(log_id)
            if result is None:
                raise InvestigationNotFound()
            return result
        except StorageUnavailable as exc:
            raise InvestigationUnavailable() from exc

    def queue(self, log_id):
        from storage import StorageUnavailable
        current = self.get(log_id)
        if current.get("status") in ("completed", "processing", "queued", "disabled"):
            return current
        try:
            return self.store.enqueue(log_id)
        except StorageUnavailable as exc:
            raise InvestigationUnavailable() from exc


def create_investigations(store):
    return StoreInvestigations(store)
