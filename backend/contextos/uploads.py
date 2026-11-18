"""Account-owned original uploads and private previews."""

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
IMAGE_ALLOWED = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}
MAX_IMAGE_BYTES = 20 * 1024 * 1024
MAX_PDF_BYTES = 50 * 1024 * 1024


def valid_image(data: bytes, mime_type: str) -> bool:
    if mime_type == "image/png":
        return data.startswith(b"\x89PNG\r\n\x1a\n") and data.endswith(b"IEND\xaeB`\x82")
    if mime_type == "image/jpeg":
        return data.startswith(b"\xff\xd8\xff") and data.endswith(b"\xff\xd9")
    return (len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP"
            and int.from_bytes(data[4:8], "little") == len(data) - 8)


@router.post("/image", status_code=201)
async def upload_image(request: Request, filename: str = Query(min_length=1, max_length=255),
                       session: dict = Depends(write_session),
                       content_length: int | None = Header(default=None, ge=0)) -> dict:
    name = Path(filename).name
    extension = Path(name).suffix.lower()
    if name != filename or extension not in IMAGE_ALLOWED:
        raise HTTPException(415, detail="Choose a PNG, JPEG, or WebP image")
    title = Path(name).stem.strip()[:240]
    if not title:
        raise HTTPException(422, detail="Image needs a name")
    if content_length is not None and content_length > MAX_IMAGE_BYTES:
        raise HTTPException(413, detail="Image exceeds 20 MiB")
    chunks, size = [], 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > MAX_IMAGE_BYTES:
            raise HTTPException(413, detail="Image exceeds 20 MiB")
        chunks.append(chunk)
    data = b"".join(chunks)
    mime_type = IMAGE_ALLOWED[extension]
    if not valid_image(data, mime_type):
        raise HTTPException(422, detail="Image content does not match its file type")
    account_id = session["account_id"]
    memory_id, asset_id = uuid.uuid4(), uuid.uuid4()
    key = object_key(account_id, memory_id, asset_id)
    target = path_for(key)
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        target.write_bytes(data)
        with connection() as db:
            row = db.execute("""INSERT INTO memories (id, account_id, kind, title, captured_at, status)
                VALUES (%s, %s, 'image', %s, %s, 'partial')
                RETURNING id, kind, title, captured_at, status, created_at""",
                (memory_id, account_id, title, datetime.now(timezone.utc))).fetchone()
            db.execute("""INSERT INTO memory_assets (id, account_id, memory_id, role, object_key,
                mime_type, byte_size, sha256, source_filename)
                VALUES (%s, %s, %s, 'original', %s, %s, %s, %s, %s)""",
                (asset_id, account_id, memory_id, key, mime_type, size,
                 hashlib.sha256(data).hexdigest(), name))
    except BaseException:
        delete(key)
        raise
    return {"data": row, "error": None}


@router.post("/pdf", status_code=201)
async def upload_pdf(request: Request, filename: str = Query(min_length=1, max_length=255),
                     session: dict = Depends(write_session),
                     content_length: int | None = Header(default=None, ge=0)) -> dict:
    name = Path(filename).name
    if name != filename or Path(name).suffix.lower() != ".pdf":
        raise HTTPException(415, detail="Choose a PDF file")
    title = Path(name).stem.strip()[:240]
    if not title:
        raise HTTPException(422, detail="PDF needs a name")
    if content_length is not None and content_length > MAX_PDF_BYTES:
        raise HTTPException(413, detail="PDF exceeds 50 MiB")
    account_id = session["account_id"]
    memory_id, asset_id, job_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    key = object_key(account_id, memory_id, asset_id)
    target = path_for(key)
    target.parent.mkdir(parents=True, exist_ok=True)
    digest, size = hashlib.sha256(), 0
    prefix = bytearray()
    try:
        with target.open("xb") as output:
            async for chunk in request.stream():
                size += len(chunk)
                if size > MAX_PDF_BYTES:
                    raise HTTPException(413, detail="PDF exceeds 50 MiB")
                if len(prefix) < 8:
                    prefix.extend(chunk[:8 - len(prefix)])
                digest.update(chunk)
                output.write(chunk)
        if not prefix.startswith(b"%PDF-") or size < 8:
            raise HTTPException(422, detail="File does not contain a PDF")
        with connection() as db:
            row = db.execute("""INSERT INTO memories (id, account_id, kind, title, captured_at, status)
                VALUES (%s, %s, 'pdf', %s, %s, 'pending')
                RETURNING id, kind, title, captured_at, status, created_at""",
                (memory_id, account_id, title, datetime.now(timezone.utc))).fetchone()
            db.execute("""INSERT INTO memory_assets (id, account_id, memory_id, role, object_key,
                mime_type, byte_size, sha256, source_filename)
                VALUES (%s, %s, %s, 'original', %s, 'application/pdf', %s, %s, %s)""",
                (asset_id, account_id, memory_id, key, size, digest.hexdigest(), name))
            db.execute("""INSERT INTO extraction_jobs (id, account_id, memory_id, job_type)
                VALUES (%s, %s, %s, 'extract_pdf')""", (job_id, account_id, memory_id))
    except BaseException:
        delete(key)
        raise
    return {"data": row, "error": None}


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


@router.get("/{memory_id}/preview")
def preview_image(memory_id: uuid.UUID, session: dict = Depends(current_session)):
    with connection() as db:
        asset = db.execute("""SELECT a.object_key, a.mime_type FROM memory_assets a
            JOIN memories m ON m.id = a.memory_id AND m.account_id = a.account_id
            WHERE a.memory_id = %s AND a.account_id = %s AND m.kind = 'image'
            AND a.role = 'original' AND a.storage_state = 'stored' LIMIT 1""",
            (memory_id, session["account_id"])).fetchone()
    if asset is None:
        raise HTTPException(404, detail="Image not found")
    path = path_for(asset["object_key"])
    if not path.is_file():
        raise HTTPException(404, detail="Image unavailable")
    return FileResponse(path, media_type=asset["mime_type"], headers={"X-Content-Type-Options": "nosniff"})


@router.get("/{memory_id}/screenshot")
def download_screenshot(memory_id: uuid.UUID, session: dict = Depends(current_session)):
    with connection() as db:
        asset = db.execute("""SELECT object_key, mime_type FROM memory_assets
            WHERE memory_id = %s AND account_id = %s AND role = 'screenshot' AND storage_state = 'stored'
            LIMIT 1""", (memory_id, session["account_id"])).fetchone()
    if not asset:
        raise HTTPException(404, detail="Screenshot not found")
    path = path_for(asset["object_key"])
    if not path.is_file():
        raise HTTPException(404, detail="Screenshot unavailable")
    return FileResponse(path, media_type=asset["mime_type"])
