"""WSGI log dashboard with local or persistent GCP storage."""
import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from storage import StorageUnavailable, create_store
from analytics import incident_analytics
from investigations import create_investigations, InvestigationUnavailable, InvestigationNotFound

MAX_BODY = 1024 * 1024


def create_app(database=None, store=None, analytics=None, investigations=None):
    store = store if store is not None else create_store(database)
    analytics = analytics if analytics is not None else incident_analytics
    investigations = investigations if investigations is not None else create_investigations(store)

    def respond(start_response, status, payload, content_type="application/json"):
        body = payload.encode() if isinstance(payload, str) else json.dumps(payload).encode()
        start_response(status, [("Content-Type", content_type), ("Content-Length", str(len(body))), ("X-Content-Type-Options", "nosniff"), ("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; frame-ancestors 'none'"), ("Cache-Control", "no-store")])
        return [body]

    def application(environ, start_response):
        path = environ.get("PATH_INFO", "/")
        method = environ.get("REQUEST_METHOD", "GET")
        if method == "GET" and path in ("/", "/app.js", "/style.css"):
            name, mime = {"/": ("index.html", "text/html; charset=utf-8"), "/app.js": ("app.js", "text/javascript; charset=utf-8"), "/style.css": ("style.css", "text/css; charset=utf-8")}[path]
            return respond(start_response, "200 OK", (Path(__file__).parent / "static" / name).read_text(encoding="utf-8"), mime)
        if method == "GET" and path == "/health":
            return respond(start_response, "200 OK", {"status": "ok"})
        if method == "GET" and path == "/analytics":
            return respond(start_response, "200 OK", analytics())
        if path == "/logs" and method == "POST":
            try:
                length = int(environ.get("CONTENT_LENGTH") or 0)
                if length < 1 or length > MAX_BODY:
                    return respond(start_response, "413 Payload Too Large", {"error": "Upload must be between 1 byte and 1 MiB."})
                data = json.loads(environ["wsgi.input"].read(length))
                if not isinstance(data, dict):
                    raise ValueError()
                filename, content = data.get("filename"), data.get("content")
                if not isinstance(filename, str) or not filename.lower().endswith(".txt") or len(filename) > 255 or "/" in filename or "\\" in filename:
                    raise ValueError()
                if not isinstance(content, str) or not content.strip() or "\x00" in content:
                    raise ValueError()
                content.encode("utf-8")
            except (ValueError, UnicodeError):
                return respond(start_response, "400 Bad Request", {"error": "Provide a plain .txt filename and nonempty UTF-8 content."})
            record = {"id": str(uuid.uuid4()), "filename": filename, "timestamp": datetime.now(timezone.utc).isoformat(), "status": "processed", "content": content, "error_count": sum("ERROR" in line.upper() for line in content.splitlines()), "warning_count": sum("WARN" in line.upper() for line in content.splitlines())}
            try:
                store.save(record)
            except StorageUnavailable:
                return unavailable(start_response)
            try:
                record["investigation"] = investigations.queue(record["id"])
            except (InvestigationUnavailable, InvestigationNotFound):
                record["investigation"] = {"status": "dispatch_failed", "message": "Upload saved. Retry the investigation without uploading again."}
            return respond(start_response, "201 Created", record)
        if path.startswith("/logs/") and path.endswith("/investigation") and method in ("GET", "POST"):
            log_id = path.removeprefix("/logs/").removesuffix("/investigation")
            try:
                if str(uuid.UUID(log_id)) != log_id:
                    raise ValueError()
            except ValueError:
                return respond(start_response, "404 Not Found", {"error": "Log not found."})
            try:
                result = investigations.queue(log_id) if method == "POST" else investigations.get(log_id)
                return respond(start_response, "202 Accepted" if method == "POST" else "200 OK", result)
            except InvestigationNotFound:
                return respond(start_response, "404 Not Found", {"error": "Log not found."})
            except InvestigationUnavailable:
                return respond(start_response, "503 Service Unavailable", {"error": "Investigation temporarily unavailable. Retry using this saved log."})
        if method == "GET" and (path == "/logs" or path.startswith("/logs/")):
            try:
                if path == "/logs":
                    return respond(start_response, "200 OK", store.list_recent())
                log_id = path.removeprefix("/logs/")
                try:
                    if str(uuid.UUID(log_id)) != log_id:
                        raise ValueError()
                except ValueError:
                    return respond(start_response, "404 Not Found", {"error": "Log not found."})
                record = store.get(log_id)
                if record:
                    return respond(start_response, "200 OK", record)
            except StorageUnavailable:
                return unavailable(start_response)
            return respond(start_response, "404 Not Found", {"error": "Log not found."})
        return respond(start_response, "404 Not Found", {"error": "Route not found."})

    def unavailable(start_response):
        # Do not log exception text: provider errors can include sensitive data.
        logging.getLogger(__name__).error("Log storage operation failed")
        return respond(start_response, "503 Service Unavailable", {"error": "Log storage is temporarily unavailable. Check recent logs before retrying an upload."})

    return application


application = create_app()
