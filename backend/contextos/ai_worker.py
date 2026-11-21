"""Retryable embedding worker, independent of extraction status and source files."""

import hashlib
import logging
from datetime import datetime, timedelta, timezone

from .ai_budget import refund, reserve, settle
from .ai_provider import EMBEDDING_MODEL, ProviderError, configured, embed
from .database import connection

log = logging.getLogger(__name__)
MAX_EMBED_CHARS = 12000


def source_for(db, account_id, memory_id):
    memory = db.execute("SELECT title, user_note FROM memories WHERE id = %s AND account_id = %s",
                        (memory_id, account_id)).fetchone()
    if memory is None:
        return None
    content = db.execute("""SELECT body FROM memory_contents WHERE memory_id = %s AND account_id = %s
        AND is_active AND provenance IN ('source', 'user', 'extracted')
        ORDER BY version DESC LIMIT 1""", (memory_id, account_id)).fetchone()
    body = "\n".join(part for part in (memory["title"], memory["user_note"],
                                  content["body"] if content else "") if part).strip()[:MAX_EMBED_CHARS]
    return body, hashlib.sha256(body.encode("utf-8")).hexdigest()


def run_once(account_id=None) -> bool:
    if not configured():
        return False
    with connection() as db:
        job = db.execute("""SELECT j.account_id, j.memory_id, j.attempt_count, j.max_attempts
            FROM ai_embedding_jobs j JOIN ai_preferences p ON p.account_id = j.account_id AND p.enabled
            WHERE j.next_retry_at <= now() AND (j.status = 'pending' OR
                  (j.status = 'processing' AND j.lease_until < now()))
              AND j.attempt_count < j.max_attempts
              AND (%s::uuid IS NULL OR j.account_id = %s::uuid)
            ORDER BY j.next_retry_at, j.updated_at FOR UPDATE OF j SKIP LOCKED LIMIT 1""",
            (account_id, account_id)).fetchone()
        if job is None:
            return False
        db.execute("""UPDATE ai_embedding_jobs SET status = 'processing', attempt_count = attempt_count + 1,
            lease_until = now() + interval '3 minutes', updated_at = now()
            WHERE account_id = %s AND memory_id = %s""", (job["account_id"], job["memory_id"]))
        source = source_for(db, job["account_id"], job["memory_id"])
        prior = db.execute("""SELECT source_sha256 FROM memory_embeddings
            WHERE account_id = %s AND memory_id = %s AND model = %s""",
            (job["account_id"], job["memory_id"], EMBEDDING_MODEL)).fetchone()
    if source is None:
        return True
    text, digest = source
    if prior and prior["source_sha256"] == digest:
        with connection() as db:
            db.execute("""UPDATE ai_embedding_jobs SET status = 'ready', lease_until = NULL,
                error_code = NULL, updated_at = now() WHERE account_id = %s AND memory_id = %s""",
                (job["account_id"], job["memory_id"]))
        return True
    estimate = len(text.encode("utf-8")) + 100
    reserved = False
    try:
        reserve(job["account_id"], estimate)
        reserved = True
        vector, tokens = embed(text)
        settle(job["account_id"], estimate, tokens)
        reserved = False
        with connection() as db:
            active = db.execute("SELECT enabled FROM ai_preferences WHERE account_id = %s",
                                (job["account_id"],)).fetchone()
            current = source_for(db, job["account_id"], job["memory_id"])
            if not active or not active["enabled"]:
                db.execute("DELETE FROM ai_embedding_jobs WHERE account_id = %s AND memory_id = %s",
                           (job["account_id"], job["memory_id"]))
            elif current and current[1] != digest:
                db.execute("""UPDATE ai_embedding_jobs SET status = 'pending', attempt_count = 0,
                    lease_until = NULL, next_retry_at = now(), updated_at = now()
                    WHERE account_id = %s AND memory_id = %s""", (job["account_id"], job["memory_id"]))
            elif current:
                db.execute("""INSERT INTO memory_embeddings
                    (account_id, memory_id, model, source_sha256, embedding, input_tokens)
                    VALUES (%s, %s, %s, %s, %s::vector, %s)
                    ON CONFLICT (account_id, memory_id, model) DO UPDATE SET
                    source_sha256 = EXCLUDED.source_sha256, embedding = EXCLUDED.embedding,
                    input_tokens = EXCLUDED.input_tokens, created_at = now()""",
                    (job["account_id"], job["memory_id"], EMBEDDING_MODEL, digest,
                     "[" + ",".join(str(value) for value in vector) + "]", tokens))
                db.execute("""UPDATE ai_embedding_jobs SET status = 'ready', lease_until = NULL,
                    error_code = NULL, updated_at = now() WHERE account_id = %s AND memory_id = %s""",
                    (job["account_id"], job["memory_id"]))
    except Exception as exc:
        if reserved:
            refund(job["account_id"], estimate)
        code = "over_budget" if getattr(exc, "status_code", None) == 429 else (
            "provider_unavailable" if isinstance(exc, ProviderError) else "embedding_failed")
        attempts = job["attempt_count"] + 1
        with connection() as db:
            db.execute("""UPDATE ai_embedding_jobs SET status = %s, error_code = %s,
                lease_until = NULL, next_retry_at = %s, updated_at = now()
                WHERE account_id = %s AND memory_id = %s""",
                ("failed" if code == "over_budget" or attempts >= job["max_attempts"] else "pending",
                 code, datetime.now(timezone.utc) + timedelta(seconds=30 * 2 ** attempts),
                 job["account_id"], job["memory_id"]))
        log.warning("Embedding job failed: %s", code)
    return True
