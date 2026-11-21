"""Explicit, reversible consent for cloud AI processing."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .ai_provider import ANSWER_MODEL, EMBEDDING_MODEL, configured
from .ai_budget import month_start
from .auth import current_session, write_session
from .database import connection

router = APIRouter(prefix="/v1/ai", tags=["ai"])


class PreferencesUpdate(BaseModel):
    enabled: bool
    monthly_token_limit: int = Field(ge=0, le=10000000)
    confirm_cloud_processing: bool = False
    delete_derived_data: bool = False


def settings_for(db, account_id):
    settings = db.execute("SELECT enabled, provider, monthly_token_limit, consented_at FROM ai_preferences WHERE account_id = %s",
                          (account_id,)).fetchone()
    usage = db.execute("SELECT used_tokens, reserved_tokens FROM ai_usage WHERE account_id = %s AND month = %s",
                       (account_id, month_start())).fetchone()
    return {"enabled": settings["enabled"] if settings else False,
            "provider": "openai", "configured": configured(),
            "embedding_model": EMBEDDING_MODEL, "answer_model": ANSWER_MODEL,
            "monthly_token_limit": settings["monthly_token_limit"] if settings else 0,
            "used_tokens": usage["used_tokens"] if usage else 0,
            "reserved_tokens": usage["reserved_tokens"] if usage else 0,
            "consented_at": settings["consented_at"] if settings else None,
            "disclosure": "When enabled, titles, notes, saved or extracted text and your questions may be sent to OpenAI for embeddings and answers. Context OS does not opt your content into model training. Core features work with AI off."}


@router.get("/settings")
def get_settings(session: dict = Depends(current_session)) -> dict:
    with connection() as db:
        result = settings_for(db, session["account_id"])
    return {"data": result, "error": None}


@router.put("/settings")
def update_settings(payload: PreferencesUpdate, session: dict = Depends(write_session)) -> dict:
    if payload.enabled and payload.monthly_token_limit == 0:
        raise HTTPException(422, detail="Set a nonzero monthly token limit")
    account_id = session["account_id"]
    with connection() as db:
        existing = db.execute("SELECT enabled FROM ai_preferences WHERE account_id = %s FOR UPDATE",
                              (account_id,)).fetchone()
        if payload.enabled and not (existing and existing["enabled"]) and not payload.confirm_cloud_processing:
            raise HTTPException(422, detail="Confirm cloud processing before enabling AI")
        if payload.enabled and not configured():
            raise HTTPException(503, detail="AI provider is not configured on this server")
        db.execute("""INSERT INTO ai_preferences(account_id, enabled, monthly_token_limit, consented_at)
            VALUES (%s, %s, %s, CASE WHEN %s THEN now() ELSE NULL END)
            ON CONFLICT (account_id) DO UPDATE SET enabled = EXCLUDED.enabled,
            monthly_token_limit = EXCLUDED.monthly_token_limit,
            consented_at = CASE WHEN EXCLUDED.enabled THEN coalesce(ai_preferences.consented_at, now())
                                 ELSE ai_preferences.consented_at END, updated_at = now()""",
            (account_id, payload.enabled, payload.monthly_token_limit, payload.enabled))
        if payload.enabled:
            db.execute("""INSERT INTO ai_embedding_jobs(account_id, memory_id)
                SELECT m.account_id, m.id FROM memories m WHERE m.account_id = %s
                ON CONFLICT (account_id, memory_id) DO UPDATE SET status = 'pending',
                next_retry_at = now(), error_code = NULL, updated_at = now()""", (account_id,))
        elif payload.delete_derived_data:
            db.execute("DELETE FROM memory_embeddings WHERE account_id = %s", (account_id,))
            db.execute("DELETE FROM ai_artifacts WHERE account_id = %s", (account_id,))
            db.execute("DELETE FROM ai_suggestions WHERE account_id = %s", (account_id,))
            db.execute("DELETE FROM ai_embedding_jobs WHERE account_id = %s", (account_id,))
        result = settings_for(db, account_id)
    return {"data": result, "error": None}
