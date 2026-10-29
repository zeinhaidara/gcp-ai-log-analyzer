"""Queue investigations after durable uploads and expose safe result fields."""


class InvestigationUnavailable(Exception):
    pass


class InvestigationNotFound(Exception):
    pass


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
