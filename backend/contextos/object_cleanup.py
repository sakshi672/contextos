"""Retry local object removal after a memory is deleted."""

import logging
from datetime import datetime, timedelta, timezone

from .database import connection
from .storage import delete as delete_object

log = logging.getLogger(__name__)


def cleanup_one(account_id=None, object_key=None) -> bool:
    # Hold the row lock through unlink so concurrent workers cannot take it.
    with connection() as db:
        row = db.execute("""
            SELECT id, object_key, attempt_count FROM object_deletions
            WHERE next_retry_at <= now() AND (%s::uuid IS NULL OR account_id = %s::uuid)
              AND (%s::text IS NULL OR object_key = %s::text)
            ORDER BY next_retry_at, created_at FOR UPDATE SKIP LOCKED LIMIT 1
        """, (account_id, account_id, object_key, object_key)).fetchone()
        if row is None:
            return False
        try:
            delete_object(row["object_key"])
        except OSError as exc:
            delay = min(3600, 15 * 2 ** min(row["attempt_count"], 8))
            db.execute("""
                UPDATE object_deletions SET attempt_count = attempt_count + 1,
                    next_retry_at = %s, last_error = %s WHERE id = %s
            """, (datetime.now(timezone.utc) + timedelta(seconds=delay),
                  type(exc).__name__, row["id"]))
            log.warning("Object cleanup %s will retry after %s", row["id"], delay)
        else:
            db.execute("DELETE FROM object_deletions WHERE id = %s", (row["id"],))
    return True
