"""Small WSGI log dashboard. Cloud integrations are added in later phases."""
import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from contextlib import closing
from pathlib import Path

MAX_BODY = 1024 * 1024


def create_app(database=None):
    database = database or os.environ.get("DATABASE_PATH", "data/logs.db")
    Path(database).parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(database)) as db, db:
        db.execute("CREATE TABLE IF NOT EXISTS logs (id TEXT PRIMARY KEY, filename TEXT, timestamp TEXT, status TEXT, content TEXT, error_count INTEGER, warning_count INTEGER)")

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
            except (ValueError, UnicodeDecodeError):
                return respond(start_response, "400 Bad Request", {"error": "Provide a plain .txt filename and nonempty UTF-8 content."})
            record = {"id": str(uuid.uuid4()), "filename": filename, "timestamp": datetime.now(timezone.utc).isoformat(), "status": "processed", "content": content, "error_count": sum("ERROR" in line.upper() for line in content.splitlines()), "warning_count": sum("WARN" in line.upper() for line in content.splitlines())}
            with closing(sqlite3.connect(database)) as db, db:
                db.execute("INSERT INTO logs VALUES (?, ?, ?, ?, ?, ?, ?)", tuple(record.values()))
            return respond(start_response, "201 Created", record)
        if method == "GET" and (path == "/logs" or path.startswith("/logs/")):
            with closing(sqlite3.connect(database)) as db, db:
                db.row_factory = sqlite3.Row
                if path == "/logs":
                    records = db.execute("SELECT id, filename, timestamp, status, error_count, warning_count FROM logs ORDER BY timestamp DESC LIMIT 100").fetchall()
                    return respond(start_response, "200 OK", [dict(row) for row in records])
                row = db.execute("SELECT * FROM logs WHERE id = ?", (path.removeprefix("/logs/"),)).fetchone()
                if row:
                    return respond(start_response, "200 OK", dict(row))
            return respond(start_response, "404 Not Found", {"error": "Log not found."})
        return respond(start_response, "404 Not Found", {"error": "Route not found."})

    return application


application = create_app()
