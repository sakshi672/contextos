"""Account-level token ceiling, checked before every provider request."""

from datetime import date, datetime, timezone

from fastapi import HTTPException

from .database import connection


def month_start() -> date:
    today = datetime.now(timezone.utc).date()
    return today.replace(day=1)


def reserve(account_id, estimate: int) -> None:
    if estimate < 1 or estimate > 100000:
        raise HTTPException(422, detail="AI request exceeds the per-request limit")
    with connection() as db:
        settings = db.execute("SELECT enabled, monthly_token_limit FROM ai_preferences WHERE account_id = %s FOR UPDATE",
                              (account_id,)).fetchone()
        if not settings or not settings["enabled"]:
            raise HTTPException(403, detail="AI is disabled for this account")
        db.execute("INSERT INTO ai_usage(account_id, month) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                   (account_id, month_start()))
        usage = db.execute("SELECT used_tokens, reserved_tokens FROM ai_usage WHERE account_id = %s AND month = %s FOR UPDATE",
                           (account_id, month_start())).fetchone()
        if usage["used_tokens"] + usage["reserved_tokens"] + estimate > settings["monthly_token_limit"]:
            raise HTTPException(429, detail="Monthly AI usage limit reached")
        db.execute("UPDATE ai_usage SET reserved_tokens = reserved_tokens + %s WHERE account_id = %s AND month = %s",
                   (estimate, account_id, month_start()))


def settle(account_id, estimate: int, actual: int) -> None:
    with connection() as db:
        db.execute("""UPDATE ai_usage SET reserved_tokens = greatest(0, reserved_tokens - %s),
            used_tokens = used_tokens + %s WHERE account_id = %s AND month = %s""",
            (estimate, max(0, actual), account_id, month_start()))


def refund(account_id, estimate: int) -> None:
    settle(account_id, estimate, 0)
