"""Worker handler for privately stored UTF-8 text and Markdown originals."""

import hashlib
import uuid

from .database import connection
from .storage import path_for


class PermanentExtractionError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def handle(job: dict) -> None:
    with connection() as db:
        asset = db.execute(
            "SELECT object_key, sha256 FROM memory_assets "
            "WHERE memory_id = %s AND account_id = %s AND role = 'original' AND storage_state = 'stored'",
            (job["memory_id"], job["account_id"]),
        ).fetchone()
    if asset is None:
        raise PermanentExtractionError("missing_original")
    try:
        data = path_for(asset["object_key"]).read_bytes()
    except FileNotFoundError as exc:
        raise PermanentExtractionError("missing_original_file") from exc
    if hashlib.sha256(data).hexdigest() != asset["sha256"]:
        raise PermanentExtractionError("checksum_mismatch")
    try:
        body = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise PermanentExtractionError("invalid_text_encoding") from exc
    if "\x00" in body:
        raise PermanentExtractionError("binary_content")
    content_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()
    with connection() as db:
        latest = db.execute(
            "SELECT version, content_sha256 FROM memory_contents "
            "WHERE memory_id = %s AND account_id = %s AND provenance = 'extracted' "
            "ORDER BY version DESC LIMIT 1 FOR UPDATE",
            (job["memory_id"], job["account_id"]),
        ).fetchone()
        if latest is None or latest["content_sha256"] != content_hash:
            db.execute(
                "UPDATE memory_contents SET is_active = false "
                "WHERE memory_id = %s AND account_id = %s AND provenance = 'extracted' AND is_active",
                (job["memory_id"], job["account_id"]),
            )
            db.execute(
                "INSERT INTO memory_contents (id, account_id, memory_id, version, provenance, body, "
                "content_sha256, processor_version, status, is_active) "
                "VALUES (%s, %s, %s, %s, 'extracted', %s, %s, 'utf8-v1', 'ready', true)",
                (uuid.uuid4(), job["account_id"], job["memory_id"],
                 1 if latest is None else latest["version"] + 1, body, content_hash),
            )
        db.execute(
            "UPDATE memories SET status = 'ready', updated_at = now() "
            "WHERE id = %s AND account_id = %s",
            (job["memory_id"], job["account_id"]),
        )
