"""Explicit browser-tab capture for paired extension credentials."""

import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field

from .database import connection
from .extension_auth import extension_session
from .memories import clean_title
from .storage import delete, object_key, path_for

router = APIRouter(prefix="/v1", tags=["captures"])
MAX_TEXT_BYTES = 2 * 1024 * 1024
MAX_SCREENSHOT_BYTES = 20 * 1024 * 1024


class CaptureInput(BaseModel):
    source_url: str = Field(min_length=1, max_length=2048)
    title: str = Field(min_length=1, max_length=240)
    captured_at: datetime | None = None
    readable_text: str = ""
    user_note: str = Field(default="", max_length=20000)
    extraction_reason: str | None = Field(default=None, max_length=80)
    project_name: str | None = Field(default=None, max_length=120)


class CapturePatch(BaseModel):
    user_note: str | None = Field(default=None, max_length=20000)
    project_name: str | None = Field(default=None, max_length=120)


def checked_url(value: str) -> tuple[str, str]:
    if any(character.isspace() for character in value):
        raise HTTPException(422, detail="Only HTTP and HTTPS tabs can be saved")
    try:
        parsed = urlsplit(value)
    except ValueError as exc:
        raise HTTPException(422, detail="Only HTTP and HTTPS tabs can be saved") from exc
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise HTTPException(422, detail="Only HTTP and HTTPS tabs can be saved")
    blocked = {domain.strip().lower() for domain in os.environ.get("CONTEXT_OS_CAPTURE_BLOCKED_DOMAINS", "").split(",") if domain.strip()}
    host = parsed.hostname.lower()
    if host in blocked or any(host.endswith("." + domain) for domain in blocked):
        raise HTTPException(422, detail="This site is blocked from capture")
    return value, host


def project_for(db, account_id, name: str | None):
    if name is None or not name.strip():
        return None
    normalized = name.strip()
    if len(normalized) > 120:
        raise HTTPException(422, detail="Project name is too long")
    row = db.execute("""INSERT INTO projects (id, account_id, name) VALUES (%s,%s,%s)
        ON CONFLICT (account_id, lower(name)) DO UPDATE SET name = projects.name RETURNING id""",
        (uuid.uuid4(), account_id, normalized)).fetchone()
    return row["id"]


def assign_project(db, account_id, memory_id, name: str | None):
    db.execute("DELETE FROM memory_projects WHERE account_id = %s AND memory_id = %s", (account_id, memory_id))
    project_id = project_for(db, account_id, name)
    if project_id:
        db.execute("INSERT INTO memory_projects (account_id, memory_id, project_id) VALUES (%s,%s,%s)",
                   (account_id, memory_id, project_id))


def capture_result(db, account_id, memory_id, already_saved: bool):
    row = db.execute("""SELECT id, title, source_uri, captured_at, status, user_note, capture_reason FROM memories
        WHERE id = %s AND account_id = %s""", (memory_id, account_id)).fetchone()
    project = db.execute("""SELECT p.name FROM memory_projects mp JOIN projects p ON p.id = mp.project_id
        WHERE mp.account_id = %s AND mp.memory_id = %s LIMIT 1""", (account_id, memory_id)).fetchone()
    content = db.execute("""SELECT 1 FROM memory_contents WHERE account_id = %s AND memory_id = %s
        AND provenance = 'source' AND is_active LIMIT 1""", (account_id, memory_id)).fetchone()
    return {"memory": row, "already_saved": already_saved, "text_saved": bool(content),
            "project_name": project["name"] if project else None}


@router.post("/captures", status_code=201)
def create_capture(payload: CaptureInput, idempotency_key: str | None = Header(default=None),
                   session: dict = Depends(extension_session)) -> dict:
    uri, domain = checked_url(payload.source_url)
    title = clean_title(payload.title)
    if len(payload.readable_text.encode("utf-8")) > MAX_TEXT_BYTES:
        raise HTTPException(413, detail="Page text exceeds 2 MiB")
    if payload.captured_at and (payload.captured_at.tzinfo is None or payload.captured_at.year < 1970):
        raise HTTPException(422, detail="Capture time needs a timezone")
    if idempotency_key and len(idempotency_key) > 128:
        raise HTTPException(422, detail="Idempotency key is too long")
    account_id = session["account_id"]
    body_hash = hashlib.sha256(json.dumps(payload.model_dump(mode="json"), sort_keys=True).encode()).hexdigest()
    content_hash = hashlib.sha256(payload.readable_text.encode("utf-8")).hexdigest() if payload.readable_text else None
    with connection() as db:
        db.execute("SELECT id FROM accounts WHERE id = %s FOR UPDATE", (account_id,))
        if idempotency_key:
            prior_request = db.execute("SELECT request_hash, memory_id FROM capture_requests WHERE account_id = %s AND request_key = %s",
                                       (account_id, idempotency_key)).fetchone()
            if prior_request:
                if prior_request["request_hash"] != body_hash:
                    raise HTTPException(409, detail="Idempotency key was already used for a different capture")
                return {"data": capture_result(db, account_id, prior_request["memory_id"], True), "error": None}
        prior = db.execute("""SELECT m.id, m.user_note, c.content_sha256 FROM memories m
            LEFT JOIN memory_contents c ON c.memory_id = m.id AND c.provenance = 'source' AND c.is_active
            WHERE m.account_id = %s AND m.kind = 'web_page' AND m.source_uri = %s
            ORDER BY m.captured_at DESC, m.id DESC LIMIT 1""", (account_id, uri)).fetchone()
        if prior and prior["user_note"] == payload.user_note and prior["content_sha256"] == content_hash:
            memory_id = prior["id"]
            already_saved = True
        else:
            memory_id = uuid.uuid4()
            already_saved = False
            db.execute("""INSERT INTO memories (id, account_id, kind, title, source_uri, source_domain,
                captured_at, status, user_note, capture_reason) VALUES (%s,%s,'web_page',%s,%s,%s,%s,%s,%s,%s)""",
                (memory_id, account_id, title, uri, domain, payload.captured_at or datetime.now(timezone.utc),
                 "ready" if content_hash else "partial", payload.user_note,
                 None if content_hash else payload.extraction_reason or "no_readable_text"))
            if content_hash:
                db.execute("""INSERT INTO memory_contents (id, account_id, memory_id, version, provenance,
                    body, content_sha256, processor_version, status, is_active)
                    VALUES (%s,%s,%s,1,'source',%s,%s,'browser-v1','ready',true)""",
                    (uuid.uuid4(), account_id, memory_id, payload.readable_text, content_hash))
        if payload.project_name is not None:
            assign_project(db, account_id, memory_id, payload.project_name)
        if idempotency_key:
            db.execute("INSERT INTO capture_requests (account_id, request_key, request_hash, memory_id) VALUES (%s,%s,%s,%s)",
                       (account_id, idempotency_key, body_hash, memory_id))
        result = capture_result(db, account_id, memory_id, already_saved)
    return {"data": result, "error": None}


@router.patch("/extension/captures/{memory_id}")
def edit_capture(memory_id: uuid.UUID, payload: CapturePatch,
                 session: dict = Depends(extension_session)) -> dict:
    if not payload.model_fields_set:
        raise HTTPException(422, detail="No changes supplied")
    with connection() as db:
        row = db.execute("SELECT id FROM memories WHERE id = %s AND account_id = %s AND kind = 'web_page' FOR UPDATE",
                         (memory_id, session["account_id"])).fetchone()
        if not row:
            raise HTTPException(404, detail="Capture not found")
        if "user_note" in payload.model_fields_set:
            db.execute("UPDATE memories SET user_note = %s, updated_at = now() WHERE id = %s AND account_id = %s",
                       (payload.user_note or "", memory_id, session["account_id"]))
        if "project_name" in payload.model_fields_set:
            assign_project(db, session["account_id"], memory_id, payload.project_name)
        result = capture_result(db, session["account_id"], memory_id, False)
    return {"data": result, "error": None}


@router.get("/extension/projects")
def list_capture_projects(session: dict = Depends(extension_session)) -> dict:
    with connection() as db:
        rows = db.execute("SELECT name FROM projects WHERE account_id = %s ORDER BY lower(name) LIMIT 100",
                          (session["account_id"],)).fetchall()
    return {"data": {"names": [row["name"] for row in rows]}, "error": None}


@router.post("/extension/captures/{memory_id}/screenshot", status_code=201)
async def save_screenshot(memory_id: uuid.UUID, request: Request,
                          session: dict = Depends(extension_session)) -> dict:
    content_type = request.headers.get("content-type", "").split(";")[0].lower()
    if content_type not in {"image/png", "image/jpeg"}:
        raise HTTPException(415, detail="Screenshot must be PNG or JPEG")
    chunks, size = [], 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > MAX_SCREENSHOT_BYTES:
            raise HTTPException(413, detail="Screenshot exceeds 20 MiB")
        chunks.append(chunk)
    body = b"".join(chunks)
    valid_png = body.startswith(b"\x89PNG\r\n\x1a\n\x00\x00\x00\x0dIHDR") and body.endswith(b"IEND\xaeB`\x82")
    valid_jpeg = body.startswith(b"\xff\xd8\xff") and body.endswith(b"\xff\xd9")
    if not body or not (valid_png if content_type == "image/png" else valid_jpeg):
        raise HTTPException(422, detail="Invalid screenshot image")
    account_id = session["account_id"]
    asset_id = uuid.uuid4()
    key = object_key(account_id, memory_id, asset_id)
    try:
        with connection() as db:
            row = db.execute("SELECT id FROM memories WHERE id = %s AND account_id = %s AND kind = 'web_page' FOR UPDATE",
                             (memory_id, account_id)).fetchone()
            if not row:
                raise HTTPException(404, detail="Capture not found")
            existing = db.execute("SELECT id FROM memory_assets WHERE memory_id = %s AND account_id = %s AND role = 'screenshot'",
                                  (memory_id, account_id)).fetchone()
            if existing:
                return {"data": {"saved": True, "already_saved": True}, "error": None}
            target = path_for(key)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(body)
            db.execute("""INSERT INTO memory_assets (id, account_id, memory_id, role, object_key, mime_type,
                byte_size, sha256, source_filename) VALUES (%s,%s,%s,'screenshot',%s,%s,%s,%s,%s)""",
                (asset_id, account_id, memory_id, key, content_type, size, hashlib.sha256(body).hexdigest(),
                 "visible-tab.png" if content_type == "image/png" else "visible-tab.jpg"))
    except BaseException:
        delete(key)
        raise
    return {"data": {"saved": True, "already_saved": False}, "error": None}
