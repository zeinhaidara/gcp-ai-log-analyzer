"""Fixed, bounded BigQuery reporting queries with a shared cache."""
import logging
import os
import re
import threading
import time
from collections import defaultdict

_lock = threading.Lock()
_cached = None
_expires = 0


def incident_analytics():
    global _cached, _expires
    table = os.getenv("BIGQUERY_TABLE", "")
    if os.getenv("STORAGE_BACKEND", "sqlite") != "gcp" or not table:
        return {"enabled": False, "message": "Incident reporting is available in the cloud deployment."}
    if not re.fullmatch(r"[a-z][a-z0-9-]+\.[A-Za-z0-9_]+\.[A-Za-z0-9_]+", table):
        raise ValueError("Invalid analytics table configuration")
    from google.cloud import bigquery
    from google.api_core.exceptions import GoogleAPICallError
    from google.auth.exceptions import GoogleAuthError
    with _lock:
        if _cached is not None and time.monotonic() < _expires:
            return _cached
        try:
            client = bigquery.Client(project=os.environ["GOOGLE_CLOUD_PROJECT"])
            config = bigquery.QueryJobConfig(maximum_bytes_billed=52428800)
            # BigQuery cannot parameterize identifiers; table passed the strict allowlist above.
            query = f"""SELECT DATE(completed_at) AS day, severity,
                COALESCE(service_name, 'unknown') AS service_name,
                COALESCE(failure_category, 'unclassified') AS failure_category,
                COUNT(DISTINCT log_id) AS incidents
                FROM `{table}`
                WHERE completed_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)
                GROUP BY day, severity, service_name, failure_category
                ORDER BY day"""  # nosec B608 - validated configuration identifier; no user SQL
            rows = client.query(query, job_config=config, location=os.getenv("BIGQUERY_LOCATION", "us-central1")).result(timeout=20)
            daily, severity, categories, services = defaultdict(int), defaultdict(int), defaultdict(int), defaultdict(int)
            for row in rows:
                count = int(row.incidents)
                daily[str(row.day)] += count
                severity[row.severity] += count
                categories[row.failure_category] += count
                services[row.service_name] += count
            _cached = {"enabled": True, "days": 7, "total": sum(severity.values()),
                       "severity": dict(severity), "daily": dict(sorted(daily.items())),
                       "categories": dict(sorted(categories.items(), key=lambda item: -item[1])[:10]),
                       "services": dict(sorted(services.items(), key=lambda item: -item[1])[:10])}
            _expires = time.monotonic() + 60
            return _cached
        except (GoogleAPICallError, GoogleAuthError, TimeoutError):
            logging.error("Incident reporting query unavailable")
            # Cache failures too, so public refresh requests do not repeatedly submit jobs.
            _cached = {"enabled": False, "message": "Incident reporting is temporarily unavailable."}
            _expires = time.monotonic() + 60
            return _cached
