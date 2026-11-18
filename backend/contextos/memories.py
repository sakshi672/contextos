"""Account-scoped note/link records for the first PostgreSQL workflow."""

import uuid
from datetime import datetime, timezone
from typing import Literal
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from .auth import current_session, write_session
from .database import connection
from .object_cleanup import cleanup_one

router = APIRouter(prefix="/v1/memories", tags=["memories"])
FIELDS = "id, kind, title, source_uri, source_domain, captured_at, status, user_note, capture_reason, created_at, updated_at"


class MemoryInput(BaseModel):
    kind: Literal["note", "link"]
    title: str = Field(min_length=1, max_length=240)
    source_uri: str | None = Field(default=None, max_length=2048)
    user_note: str = Field(default="", max_length=20000)


class MemoryPatch(BaseModel):
    kind: Literal["note", "link"] | None = None
    title: str | None = Field(default=None, min_length=1, max_length=240)
    source_uri: str | None = Field(default=None, max_length=2048)
    user_note: str | None = Field(default=None, max_length=20000)


def source_domain(kind: str, source_uri: str | None) -> str | None:
    if kind == "note":
        if source_uri:
            raise HTTPException(422, detail="Notes cannot have a source URL")
        return None
    if not source_uri:
        raise HTTPException(422, detail="Links need an HTTP or HTTPS URL")
    parsed = urlsplit(source_uri)
    if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password:
        raise HTTPException(422, detail="Enter a valid HTTP or HTTPS URL")
    return parsed.hostname.lower()


def clean_title(value: str) -> str:
    title = value.strip()
    if not title:
        raise HTTPException(422, detail="Title cannot be empty")
    return title


@router.post("", status_code=201)
def create_memory(payload: MemoryInput, session: dict = Depends(write_session)) -> dict:
    title = clean_title(payload.title)
    domain = source_domain(payload.kind, payload.source_uri)
    memory_id = uuid.uuid4()
    with connection() as db:
        row = db.execute(
            f"INSERT INTO memories (id, account_id, kind, title, source_uri, source_domain, captured_at, status, user_note) "
            f"VALUES (%s, %s, %s, %s, %s, %s, %s, 'ready', %s) RETURNING {FIELDS}",
            (memory_id, session["account_id"], payload.kind, title, payload.source_uri,
             domain, datetime.now(timezone.utc), payload.user_note),
        ).fetchone()
    return {"data": row, "error": None}


@router.get("")
def list_memories(
    session: dict = Depends(current_session),
    kind: Literal["all", "note", "link", "document", "web_page"] = "all",
    q: str = Query(default="", max_length=200),
    sort: Literal["recent", "updated", "title"] = "recent",
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict:
    # Escape LIKE metacharacters so the user's words are searched literally.
    search = "%" + q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    predicate = (
        "account_id = %s AND (%s = 'all' OR kind = %s) "
        "AND (%s = '' OR title ILIKE %s ESCAPE '\\' OR user_note ILIKE %s ESCAPE '\\' "
        "OR source_uri ILIKE %s ESCAPE '\\')"
    )
    params = (session["account_id"], kind, kind, q.strip(), search, search, search)
    ordering = {
        "recent": "captured_at DESC, id DESC",
        "updated": "updated_at DESC, id DESC",
        "title": "lower(title) ASC, id ASC",
    }[sort]
    with connection() as db:
        total = db.execute(
            f"SELECT count(*) AS total FROM memories WHERE {predicate}", params,
        ).fetchone()["total"]
        rows = db.execute(
            f"SELECT {FIELDS} FROM memories WHERE {predicate} "
            f"ORDER BY {ordering} LIMIT %s OFFSET %s",
            (*params, limit, offset),
        ).fetchall()
    return {"data": {"items": rows, "total": total, "limit": limit, "offset": offset}, "error": None}


@router.get("/{memory_id}")
def get_memory(memory_id: uuid.UUID, session: dict = Depends(current_session)) -> dict:
    with connection() as db:
        row = db.execute(
            f"SELECT {FIELDS} FROM memories WHERE id = %s AND account_id = %s",
            (memory_id, session["account_id"]),
        ).fetchone()
        if row is not None:
            row["has_screenshot"] = bool(db.execute(
                "SELECT 1 FROM memory_assets WHERE memory_id = %s AND account_id = %s AND role = 'screenshot' LIMIT 1",
                (memory_id, session["account_id"]),
            ).fetchone())
            project = db.execute("""SELECT p.name FROM memory_projects mp JOIN projects p ON p.id = mp.project_id
                WHERE mp.memory_id = %s AND mp.account_id = %s LIMIT 1""",
                (memory_id, session["account_id"]),
            ).fetchone()
            row["project_name"] = project["name"] if project else None
    if row is None:
        raise HTTPException(404, detail="Memory not found")
    return {"data": row, "error": None}


@router.get("/{memory_id}/content")
def get_extracted_content(memory_id: uuid.UUID, session: dict = Depends(current_session)) -> dict:
    with connection() as db:
        row = db.execute(
            "SELECT c.body, c.version, c.content_sha256, c.processor_version "
            "FROM memory_contents c JOIN memories m ON m.id = c.memory_id AND m.account_id = c.account_id "
            "WHERE c.memory_id = %s AND c.account_id = %s AND c.provenance IN ('extracted', 'source') AND c.is_active "
            "ORDER BY c.version DESC LIMIT 1",
            (memory_id, session["account_id"]),
        ).fetchone()
    if row is None:
        raise HTTPException(404, detail="Extracted content not found")
    return {"data": row, "error": None}


@router.patch("/{memory_id}")
def update_memory(memory_id: uuid.UUID, payload: MemoryPatch, session: dict = Depends(write_session)) -> dict:
    if not payload.model_fields_set:
        raise HTTPException(422, detail="No changes supplied")
    with connection() as db:
        existing = db.execute(
            "SELECT kind, source_uri FROM memories WHERE id = %s AND account_id = %s",
            (memory_id, session["account_id"]),
        ).fetchone()
        if existing is None:
            raise HTTPException(404, detail="Memory not found")
        title = clean_title(payload.title) if "title" in payload.model_fields_set and payload.title is not None else None
        if "title" in payload.model_fields_set and payload.title is None:
            raise HTTPException(422, detail="Title cannot be empty")
        kind = payload.kind if payload.kind is not None else existing["kind"]
        uri = payload.source_uri if "source_uri" in payload.model_fields_set else existing["source_uri"]
        domain = source_domain(kind, uri)
        row = db.execute(
            f"UPDATE memories SET kind = %s, title = COALESCE(%s, title), source_uri = %s, source_domain = %s, "
            f"user_note = COALESCE(%s, user_note), updated_at = now() "
            f"WHERE id = %s AND account_id = %s RETURNING {FIELDS}",
            (kind, title, uri, domain, payload.user_note, memory_id, session["account_id"]),
        ).fetchone()
    return {"data": row, "error": None}


@router.delete("/{memory_id}")
def delete_memory(memory_id: uuid.UUID, session: dict = Depends(write_session)) -> dict:
    with connection() as db:
        keys = [row["object_key"] for row in db.execute(
            "SELECT object_key FROM memory_assets WHERE memory_id = %s AND account_id = %s",
            (memory_id, session["account_id"]),
        ).fetchall()]
        for key in keys:
            db.execute("INSERT INTO object_deletions (id, account_id, object_key) VALUES (%s, %s, %s)",
                       (uuid.uuid4(), session["account_id"], key))
        deleted = db.execute(
            "DELETE FROM memories WHERE id = %s AND account_id = %s",
            (memory_id, session["account_id"]),
        ).rowcount
    if not deleted:
        raise HTTPException(404, detail="Memory not found")
    for key in keys:
        cleanup_one(account_id=session["account_id"], object_key=key)
    return {"data": {"deleted": True}, "error": None}
