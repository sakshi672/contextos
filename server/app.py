"""Dependency-free local API. Not exposed publicly until account isolation is built."""

import json
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .db import connection, initialize, row_to_memory

MAX_BODY = 64 * 1024


def now():
    return datetime.now(timezone.utc).isoformat()


def validate(payload):
    if not isinstance(payload, dict):
        raise ValueError("Enter a valid memory.")
    title = str(payload.get("title", "")).strip()
    note = str(payload.get("note", "")).strip()
    kind = payload.get("kind", "note")
    source_url = str(payload.get("source_url", "")).strip()
    if not title or len(title) > 240:
        raise ValueError("Title must be between 1 and 240 characters.")
    if len(note) > 20000:
        raise ValueError("Note is too long (maximum 20,000 characters).")
    if kind not in ("note", "link"):
        raise ValueError("Choose a supported memory type.")
    if kind == "link":
        parsed = urlparse(source_url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc or len(source_url) > 2048:
            raise ValueError("Enter a valid http or https URL.")
    else:
        source_url = ""
    return {"title": title, "note": note, "kind": kind, "source_url": source_url}


def search_query(value):
    words = re.findall(r"[\w]+", value[:200], re.UNICODE)
    return " AND ".join('"' + word.replace('"', '') + '"*' for word in words[:12])


class Handler(BaseHTTPRequestHandler):
    def send_json(self, status, value):
        body = json.dumps(value).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def read_json(self):
        size = int(self.headers.get("Content-Length", "0"))
        if size < 1 or size > MAX_BODY:
            raise ValueError("The request is empty or too large.")
        try:
            return json.loads(self.rfile.read(size))
        except json.JSONDecodeError as exc:
            raise ValueError("Enter valid JSON.") from exc

    def do_GET(self):
        path = urlparse(self.path)
        if path.path == "/api/health":
            return self.send_json(200, {"status": "ok"})
        if path.path == "/api/memories":
            query = parse_qs(path.query).get("q", [""])[0].strip()
            kind = parse_qs(path.query).get("kind", ["all"])[0]
            if kind not in ("all", "note", "link"):
                return self.send_json(400, {"error": "Unsupported filter."})
            with connection() as db:
                if query and search_query(query):
                    sql = "SELECT m.* FROM memories m JOIN memory_search s ON m.id=s.id WHERE memory_search MATCH ?"
                    args = [search_query(query)]
                    if kind != "all":
                        sql += " AND m.kind=?"
                        args.append(kind)
                    sql += " ORDER BY bm25(memory_search), m.captured_at DESC LIMIT 100"
                    rows = db.execute(sql, args).fetchall()
                else:
                    sql = "SELECT * FROM memories"
                    args = []
                    if kind != "all":
                        sql += " WHERE kind=?"
                        args.append(kind)
                    rows = db.execute(sql + " ORDER BY captured_at DESC LIMIT 100", args).fetchall()
            return self.send_json(200, {"items": [row_to_memory(row) for row in rows]})
        if path.path.startswith("/api/memories/"):
            memory_id = path.path.removeprefix("/api/memories/")
            with connection() as db:
                row = db.execute("SELECT * FROM memories WHERE id=?", (memory_id,)).fetchone()
            return self.send_json(200, row_to_memory(row)) if row else self.send_json(404, {"error": "Memory not found."})
        self.send_json(404, {"error": "Not found."})

    def do_POST(self):
        if self.path != "/api/memories":
            return self.send_json(404, {"error": "Not found."})
        try:
            data = validate(self.read_json())
        except ValueError as exc:
            return self.send_json(400, {"error": str(exc)})
        memory_id, timestamp = str(uuid.uuid4()), now()
        with connection() as db:
            db.execute("INSERT INTO memories VALUES (?, ?, ?, ?, ?, ?, ?)",
                       (memory_id, data["title"], data["kind"], data["source_url"], data["note"], timestamp, timestamp))
            db.execute("INSERT INTO memory_search (id, title, note, source_url) VALUES (?, ?, ?, ?)",
                       (memory_id, data["title"], data["note"], data["source_url"]))
            row = db.execute("SELECT * FROM memories WHERE id=?", (memory_id,)).fetchone()
        self.send_json(201, row_to_memory(row))

    def do_PUT(self):
        if not self.path.startswith("/api/memories/"):
            return self.send_json(404, {"error": "Not found."})
        memory_id = self.path.removeprefix("/api/memories/")
        try:
            data = validate(self.read_json())
        except ValueError as exc:
            return self.send_json(400, {"error": str(exc)})
        with connection() as db:
            if not db.execute("SELECT 1 FROM memories WHERE id=?", (memory_id,)).fetchone():
                return self.send_json(404, {"error": "Memory not found."})
            db.execute("UPDATE memories SET title=?, kind=?, source_url=?, note=?, updated_at=? WHERE id=?",
                       (data["title"], data["kind"], data["source_url"], data["note"], now(), memory_id))
            db.execute("DELETE FROM memory_search WHERE id=?", (memory_id,))
            db.execute("INSERT INTO memory_search (id, title, note, source_url) VALUES (?, ?, ?, ?)",
                       (memory_id, data["title"], data["note"], data["source_url"]))
            row = db.execute("SELECT * FROM memories WHERE id=?", (memory_id,)).fetchone()
        self.send_json(200, row_to_memory(row))

    def do_DELETE(self):
        if not self.path.startswith("/api/memories/"):
            return self.send_json(404, {"error": "Not found."})
        memory_id = self.path.removeprefix("/api/memories/")
        with connection() as db:
            found = db.execute("DELETE FROM memories WHERE id=?", (memory_id,)).rowcount
            db.execute("DELETE FROM memory_search WHERE id=?", (memory_id,))
        self.send_json(200, {"deleted": True}) if found else self.send_json(404, {"error": "Memory not found."})


def run(host="127.0.0.1", port=8765):
    initialize()
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"Context OS API running at http://{host}:{port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    run()
