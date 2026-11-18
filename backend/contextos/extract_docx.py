"""Bounded text extraction from WordprocessingML DOCX originals."""

import hashlib
import uuid
from io import BytesIO
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile

from .database import connection
from .extract_text import PermanentExtractionError
from .storage import path_for

MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
MAX_ARCHIVE_ENTRIES = 500
MAX_EXPANDED_BYTES = 40 * 1024 * 1024
MAX_XML_BYTES = 20 * 1024 * 1024
MAX_EXTRACTED_BYTES = 10 * 1024 * 1024
WORD = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def extract(source: bytes) -> str:
    try:
        with ZipFile(BytesIO(source)) as archive:
            infos = archive.infolist()
            if (len(infos) > MAX_ARCHIVE_ENTRIES or
                    sum(item.file_size for item in infos) > MAX_EXPANDED_BYTES):
                raise PermanentExtractionError("docx_expanded_limit")
            names = {item.filename for item in infos}
            if "[Content_Types].xml" not in names or "word/document.xml" not in names:
                raise PermanentExtractionError("invalid_docx")
            document = archive.getinfo("word/document.xml")
            if document.file_size > MAX_XML_BYTES or document.flag_bits & 1:
                raise PermanentExtractionError("invalid_docx")
            xml = archive.read(document)
            if b"<!DOCTYPE" in xml.upper() or b"<!ENTITY" in xml.upper():
                raise PermanentExtractionError("invalid_docx")
            root = ElementTree.fromstring(xml)
            if root.tag != WORD + "document":
                raise PermanentExtractionError("invalid_docx")
            paragraphs = []
            for paragraph in root.iter(WORD + "p"):
                pieces = []
                for node in paragraph.iter():
                    if node.tag == WORD + "t" and node.text:
                        pieces.append(node.text)
                    elif node.tag == WORD + "tab":
                        pieces.append("\t")
                    elif node.tag in {WORD + "br", WORD + "cr"}:
                        pieces.append("\n")
                text = "".join(pieces).strip()
                if text:
                    paragraphs.append(text)
            body = "\n\n".join(paragraphs)
            if len(body.encode("utf-8")) > MAX_EXTRACTED_BYTES:
                raise PermanentExtractionError("docx_text_too_large")
            return body
    except (BadZipFile, KeyError, ElementTree.ParseError, RuntimeError, ValueError, OSError) as exc:
        raise PermanentExtractionError("invalid_docx") from exc


def handle(job: dict) -> None:
    with connection() as db:
        asset = db.execute("""SELECT object_key, sha256 FROM memory_assets
            WHERE memory_id = %s AND account_id = %s AND role = 'original'
            AND mime_type = %s AND storage_state = 'stored'""",
            (job["memory_id"], job["account_id"], MIME)).fetchone()
    if asset is None:
        raise PermanentExtractionError("missing_original")
    try:
        source = path_for(asset["object_key"]).read_bytes()
    except FileNotFoundError as exc:
        raise PermanentExtractionError("missing_original_file") from exc
    if hashlib.sha256(source).hexdigest() != asset["sha256"]:
        raise PermanentExtractionError("checksum_mismatch")
    body = extract(source)
    status = "ready" if body else "partial"
    reason = None if body else "docx_no_text"
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
            db.execute("""INSERT INTO memory_contents (id, account_id, memory_id, version,
                provenance, body, content_sha256, processor_version, status, is_active)
                VALUES (%s, %s, %s, %s, 'extracted', %s, %s, 'docx-xml-v1', 'ready', true)""",
                (uuid.uuid4(), job["account_id"], job["memory_id"],
                 1 if latest is None else latest["version"] + 1, body, content_hash))
        db.execute("""UPDATE memories SET status = %s, capture_reason = %s, updated_at = now()
            WHERE id = %s AND account_id = %s""",
            (status, reason, job["memory_id"], job["account_id"]))
