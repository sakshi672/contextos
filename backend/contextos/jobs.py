"""Durable job claims and outcomes. Payloads stay in owned database records."""

from datetime import datetime, timedelta, timezone

from .database import connection


def claim_one(lease_seconds: int = 120):
    """Atomically claim a due job, including one whose previous lease expired."""
    with connection() as db:
        row = db.execute("""
            SELECT id, account_id, memory_id, job_type, attempt_count, max_attempts
            FROM extraction_jobs
            WHERE next_retry_at <= now()
              AND (status = 'pending' OR (status = 'processing' AND lease_until < now()))
              AND attempt_count < max_attempts
            ORDER BY next_retry_at, created_at
            FOR UPDATE SKIP LOCKED
            LIMIT 1
        """).fetchone()
        if row is None:
            return None
        db.execute("""
            UPDATE extraction_jobs
            SET status = 'processing', attempt_count = attempt_count + 1,
                lease_until = %s, updated_at = now(), error_code = NULL
            WHERE id = %s
        """, (datetime.now(timezone.utc) + timedelta(seconds=lease_seconds), row["id"]))
        row["attempt_count"] += 1
        return row


def finish(job_id, account_id, *, error_code: str | None = None, retry_seconds: int = 30):
    """Complete or retry a job only if its account still owns it."""
    with connection() as db:
        if error_code is None:
            db.execute("""
                UPDATE extraction_jobs SET status = 'ready', lease_until = NULL,
                    error_code = NULL, updated_at = now()
                WHERE id = %s AND account_id = %s AND status = 'processing'
            """, (job_id, account_id))
        else:
            db.execute("""
                UPDATE extraction_jobs
                SET status = CASE WHEN attempt_count >= max_attempts THEN 'failed' ELSE 'pending' END,
                    lease_until = NULL, error_code = %s,
                    next_retry_at = %s, updated_at = now()
                WHERE id = %s AND account_id = %s AND status = 'processing'
            """, (error_code, datetime.now(timezone.utc) + timedelta(seconds=retry_seconds), job_id, account_id))
