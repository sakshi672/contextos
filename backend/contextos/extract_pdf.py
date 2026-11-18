"""Page-aware extraction of privately stored PDF originals."""

import hashlib
import uuid
from io import BytesIO

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from .database import connection
from .extract_text import PermanentExtractionError
from .storage import path_for
from .ocr import MAX_PDF_OCR_PAGES, open_pdf, recognize_pdf_page

MAX_PAGES = 200
MAX_EXTRACTED_BYTES = 10 * 1024 * 1024


def handle(job: dict) -> None:
    with connection() as db:
        asset = db.execute("""SELECT object_key, sha256 FROM memory_assets
            WHERE memory_id = %s AND account_id = %s AND role = 'original'
            AND mime_type = 'application/pdf' AND storage_state = 'stored'""",
            (job["memory_id"], job["account_id"])).fetchone()
    if asset is None:
        raise PermanentExtractionError("missing_original")
    try:
        source = path_for(asset["object_key"]).read_bytes()
    except FileNotFoundError as exc:
        raise PermanentExtractionError("missing_original_file") from exc
    if hashlib.sha256(source).hexdigest() != asset["sha256"]:
        raise PermanentExtractionError("checksum_mismatch")
    try:
        reader = PdfReader(BytesIO(source), strict=False)
        if reader.is_encrypted:
            raise PermanentExtractionError("encrypted_pdf")
        if not 1 <= len(reader.pages) <= MAX_PAGES:
            raise PermanentExtractionError("pdf_page_limit")
        pages = []
        missing_text = False
        ocr_attempts = 0
        ocr_reason = None
        rendered = None
        extracted_bytes = 0
        try:
            for number, page in enumerate(reader.pages, 1):
                text = (page.extract_text() or "").strip()
                if not text:
                    if ocr_attempts >= MAX_PDF_OCR_PAGES:
                        ocr_reason = "ocr_page_limit"
                    else:
                        ocr_attempts += 1
                        try:
                            if rendered is None:
                                rendered = open_pdf(source)
                            text = recognize_pdf_page(rendered, number - 1).strip()
                        except PermanentExtractionError:
                            ocr_reason = "ocr_failed"
                if not text:
                    missing_text = True
                else:
                    pages.append((number, text))
                    extracted_bytes += len(text.encode("utf-8"))
                if extracted_bytes > MAX_EXTRACTED_BYTES:
                    raise PermanentExtractionError("pdf_text_too_large")
        finally:
            if rendered is not None:
                rendered.close()
    except (PdfReadError, ValueError, TypeError, OSError) as exc:
        raise PermanentExtractionError("invalid_pdf") from exc
    status = "partial" if missing_text else "ready"
    reason = (ocr_reason or "no_text_detected") if missing_text else None
    body = "\n\n".join(text for _, text in pages)
    content_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()
    with connection() as db:
        latest = db.execute("""SELECT version, content_sha256 FROM memory_contents
            WHERE memory_id = %s AND account_id = %s AND provenance = 'extracted'
            ORDER BY version DESC LIMIT 1 FOR UPDATE""",
            (job["memory_id"], job["account_id"])).fetchone()
        if body and (latest is None or latest["content_sha256"] != content_hash):
            db.execute("""UPDATE memory_contents SET is_active = false
                WHERE memory_id = %s AND account_id = %s AND provenance = 'extracted' AND is_active""",
                (job["memory_id"], job["account_id"]))
            content_id = uuid.uuid4()
            db.execute("""INSERT INTO memory_contents (id, account_id, memory_id, version,
                provenance, body, content_sha256, processor_version, status, is_active)
                VALUES (%s, %s, %s, %s, 'extracted', %s, %s, 'pypdf-v1', %s, true)""",
                (content_id, job["account_id"], job["memory_id"],
                 1 if latest is None else latest["version"] + 1, body, content_hash, status))
            offset = 0
            for ordinal, (number, page_text) in enumerate(pages):
                db.execute("""INSERT INTO content_passages (id, account_id, memory_id,
                    content_id, ordinal, body, page_number, start_offset, end_offset)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                    (uuid.uuid4(), job["account_id"], job["memory_id"], content_id,
                     ordinal, page_text, number, offset, offset + len(page_text)))
                offset += len(page_text) + 2
        db.execute("""UPDATE memories SET status = %s, capture_reason = %s, updated_at = now()
            WHERE id = %s AND account_id = %s""",
            (status, reason, job["memory_id"], job["account_id"]))
