"""Owned direct uploads for small text documents in local Phase 1."""

import hashlib
import codecs
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse

from .auth import current_session, write_session
from .database import connection
from .storage import delete, object_key, path_for

router = APIRouter(prefix="/v1/uploads", tags=["uploads"])
MAX_TEXT_BYTES = 10 * 1024 * 1024
ALLOWED = {".txt": "text/plain", ".md": "text/markdown"}


@router.post("/text", status_code=201)
async def upload_text(
    request: Request,
    filename: str = Query(min_length=1, max_length=255),
    session: dict = Depends(write_session),
    content_length: int | None = Header(default=None, ge=0),
) -> dict:
    name = Path(filename).name
    extension = Path(name).suffix.lower()
    if name != filename or extension not in ALLOWED:
        raise HTTPException(415, detail="Choose a UTF-8 TXT or Markdown file")
    title = Path(name).stem.strip()[:240]
    if not title:
        raise HTTPException(422, detail="File needs a name")
    if content_length is not None and content_length > MAX_TEXT_BYTES:
        raise HTTPException(413, detail="File exceeds the 10 MiB limit")

    account_id = session["account_id"]
    memory_id, asset_id, job_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    key = object_key(account_id, memory_id, asset_id)
    target = path_for(key)
    target.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    decoder = codecs.getincrementaldecoder("utf-8-sig")()
    size = 0
    try:
        with target.open("xb") as output:
            async for chunk in request.stream():
                size += len(chunk)
                if size > MAX_TEXT_BYTES:
                    raise HTTPException(413, detail="File exceeds the 10 MiB limit")
                try:
                    decoded = decoder.decode(chunk)
                except UnicodeDecodeError as exc:
                    raise HTTPException(422, detail="File must contain UTF-8 text") from exc
                if "\x00" in decoded:
                    raise HTTPException(422, detail="File contains binary content")
                digest.update(chunk)
                output.write(chunk)
            try:
                decoder.decode(b"", final=True)
            except UnicodeDecodeError as exc:
                raise HTTPException(422, detail="File must contain UTF-8 text") from exc
        if size == 0:
            raise HTTPException(422, detail="File is empty")
        with connection() as db:
            row = db.execute(
                "INSERT INTO memories (id, account_id, kind, title, captured_at, status) "
                "VALUES (%s, %s, 'document', %s, %s, 'pending') "
                "RETURNING id, kind, title, captured_at, status, created_at",
                (memory_id, account_id, title, datetime.now(timezone.utc)),
            ).fetchone()
            db.execute(
                "INSERT INTO memory_assets (id, account_id, memory_id, role, object_key, mime_type, "
                "byte_size, sha256, source_filename) VALUES (%s, %s, %s, 'original', %s, %s, %s, %s, %s)",
                (asset_id, account_id, memory_id, key, ALLOWED[extension], size, digest.hexdigest(), name),
            )
            db.execute(
                "INSERT INTO extraction_jobs (id, account_id, memory_id, job_type) "
                "VALUES (%s, %s, %s, 'extract_text')",
                (job_id, account_id, memory_id),
            )
    except BaseException:
        delete(key)
        raise
    return {"data": row, "error": None}


@router.get("/{memory_id}/original")
def download_original(memory_id: uuid.UUID, session: dict = Depends(current_session)):
    with connection() as db:
        asset = db.execute(
            "SELECT object_key, mime_type, source_filename FROM memory_assets "
            "WHERE memory_id = %s AND account_id = %s AND role = 'original' AND storage_state = 'stored' "
            "ORDER BY created_at LIMIT 1",
            (memory_id, session["account_id"]),
        ).fetchone()
    if asset is None:
        raise HTTPException(404, detail="Original file not found")
    path = path_for(asset["object_key"])
    if not path.is_file():
        raise HTTPException(404, detail="Original file unavailable")
    return FileResponse(path, media_type=asset["mime_type"], filename=asset["source_filename"])
