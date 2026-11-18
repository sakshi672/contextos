"""OCR from an owned uploaded image, retaining its original."""

import hashlib
import uuid

from .database import connection
from .extract_text import PermanentExtractionError
from .ocr import recognize_image
from .storage import path_for

MAX_EXTRACTED_BYTES = 2 * 1024 * 1024


def handle(job: dict) -> None:
    with connection() as db:
        asset = db.execute("""SELECT object_key, sha256 FROM memory_assets
            WHERE memory_id = %s AND account_id = %s AND role = 'original'
            AND mime_type IN ('image/png', 'image/jpeg', 'image/webp') AND storage_state = 'stored'""",
            (job["memory_id"], job["account_id"])).fetchone()
    if asset is None:
        raise PermanentExtractionError("missing_original")
    try:
        source = path_for(asset["object_key"]).read_bytes()
    except FileNotFoundError as exc:
        raise PermanentExtractionError("missing_original_file") from exc
    if hashlib.sha256(source).hexdigest() != asset["sha256"]:
        raise PermanentExtractionError("checksum_mismatch")
    body = recognize_image(source).strip()
    if len(body.encode("utf-8")) > MAX_EXTRACTED_BYTES:
        raise PermanentExtractionError("ocr_text_too_large")
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
    status = "ready" if body else "partial"
    with connection() as db:
        latest = db.execute("""SELECT version, content_sha256 FROM memory_contents
            WHERE memory_id = %s AND account_id = %s AND provenance = 'extracted'
            ORDER BY version DESC LIMIT 1 FOR UPDATE""",
            (job["memory_id"], job["account_id"])).fetchone()
        if body and (latest is None or latest["content_sha256"] != digest):
            db.execute("""UPDATE memory_contents SET is_active = false WHERE memory_id = %s
                AND account_id = %s AND provenance = 'extracted' AND is_active""",
                (job["memory_id"], job["account_id"]))
            db.execute("""INSERT INTO memory_contents (id, account_id, memory_id, version,
                provenance, body, content_sha256, processor_version, status, is_active)
                VALUES (%s,%s,%s,%s,'extracted',%s,%s,'rapidocr-v1','ready',true)""",
                (uuid.uuid4(), job["account_id"], job["memory_id"],
                 1 if latest is None else latest["version"] + 1, body, digest))
        db.execute("""UPDATE memories SET status = %s, capture_reason = %s, updated_at = now()
            WHERE id = %s AND account_id = %s""",
            (status, None if body else "no_text_detected", job["memory_id"], job["account_id"]))
