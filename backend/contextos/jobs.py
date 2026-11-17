"""Durable job claims and outcomes. Payloads stay in owned database records."""

from datetime import datetime, timedelta, timezone

from .database import connection


def claim_one(lease_seconds: int = 120, account_id=None):
    """Atomically claim a due job, including one whose previous lease expired."""
    with connection() as db:
        exhausted = db.execute("""
            UPDATE extraction_jobs SET status = 'failed', error_code = 'lease_expired',
                lease_until = NULL, updated_at = now()
            WHERE status = 'processing' AND lease_until < now()
              AND attempt_count >= max_attempts
              AND (%s::uuid IS NULL OR account_id = %s::uuid)
            RETURNING memory_id, account_id
        """, (account_id, account_id)).fetchall()
        for stale in exhausted:
            db.execute(
                "UPDATE memories SET status = 'failed', updated_at = now() "
                "WHERE id = %s AND account_id = %s",
                (stale["memory_id"], stale["account_id"]),
            )
        row = db.execute("""
            SELECT id, account_id, memory_id, job_type, attempt_count, max_attempts
            FROM extraction_jobs
            WHERE next_retry_at <= now()
              AND (%s::uuid IS NULL OR account_id = %s::uuid)
              AND (status = 'pending' OR (status = 'processing' AND lease_until < now()))
              AND attempt_count < max_attempts
            ORDER BY next_retry_at, created_at
            FOR UPDATE SKIP LOCKED
            LIMIT 1
        """, (account_id, account_id)).fetchone()
        if row is None:
            return None
        db.execute("""
            UPDATE extraction_jobs
            SET status = 'processing', attempt_count = attempt_count + 1,
                lease_until = %s, updated_at = now(), error_code = NULL
            WHERE id = %s
        """, (datetime.now(timezone.utc) + timedelta(seconds=lease_seconds), row["id"]))
        db.execute(
            "UPDATE memories SET status = 'processing', updated_at = now() "
            "WHERE id = %s AND account_id = %s",
            (row["memory_id"], row["account_id"]),
        )
        row["attempt_count"] += 1
        return row


def finish(job_id, account_id, attempt_count: int, *, error_code: str | None = None,
           retry_seconds: int = 30, permanent: bool = False):
    """Complete only the currently claimed attempt of an owned job."""
    with connection() as db:
        if error_code is None:
            db.execute("""
                UPDATE extraction_jobs SET status = 'ready', lease_until = NULL,
                    error_code = NULL, updated_at = now()
                WHERE id = %s AND account_id = %s AND attempt_count = %s AND status = 'processing'
            """, (job_id, account_id, attempt_count))
        else:
            result = db.execute("""
                UPDATE extraction_jobs
                SET status = CASE WHEN %s OR attempt_count >= max_attempts THEN 'failed' ELSE 'pending' END,
                    lease_until = NULL, error_code = %s,
                    next_retry_at = %s, updated_at = now()
                WHERE id = %s AND account_id = %s AND attempt_count = %s AND status = 'processing'
                RETURNING memory_id, status
            """, (permanent, error_code, datetime.now(timezone.utc) + timedelta(seconds=retry_seconds),
                  job_id, account_id, attempt_count)).fetchone()
            if result is not None:
                db.execute(
                    "UPDATE memories SET status = %s, updated_at = now() "
                    "WHERE id = %s AND account_id = %s",
                    ("failed" if result["status"] == "failed" else "pending",
                     result["memory_id"], account_id),
                )
