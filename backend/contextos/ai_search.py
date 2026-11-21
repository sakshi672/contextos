"""Hybrid ranked retrieval with visible semantic provenance and keyword fallback."""

import uuid
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, Query

from .ai_budget import refund, reserve, settle
from .ai_provider import EMBEDDING_MODEL, ProviderError, configured, embed
from .auth import current_session
from .database import connection
from .memories import FIELDS
from .search import _FILTERS, search_memories

router = APIRouter(prefix="/v1/ai", tags=["ai"])


@router.get("/search")
def hybrid_search(q: str = Query(default="", max_length=200), session: dict = Depends(current_session),
                  kind: Literal["all", "note", "link", "document", "web_page", "snippet", "image", "pdf"] = "all",
                  domain: str | None = Query(default=None, max_length=255),
                  date_from: date | None = None, date_to: date | None = None,
                  project_id: uuid.UUID | None = None, tag_id: uuid.UUID | None = None,
                  collection_id: uuid.UUID | None = None,
                  limit: int = Query(default=20, ge=1, le=100),
                  offset: int = Query(default=0, ge=0)) -> dict:
    def words(page_limit=limit, page_offset=offset):
        return search_memories(q=q, session=session, kind=kind, domain=domain,
                               date_from=date_from, date_to=date_to, project_id=project_id,
                               tag_id=tag_id, collection_id=collection_id,
                               limit=page_limit, offset=page_offset)["data"]

    keyword = words(100, 0)
    account_id = session["account_id"]
    with connection() as db:
        preference = db.execute("SELECT enabled FROM ai_preferences WHERE account_id = %s",
                                (account_id,)).fetchone()
    if not q.strip() or not preference or not preference["enabled"] or not configured():
        keyword = words()
        keyword["ai_status"] = "disabled" if not preference or not preference["enabled"] else "unavailable"
        return {"data": keyword, "error": None}
    estimate = len(q.encode("utf-8")) + 100
    try:
        reserve(account_id, estimate)
    except Exception as exc:
        keyword = words()
        keyword["ai_status"] = "limit_reached" if getattr(exc, "status_code", None) == 429 else "unavailable"
        return {"data": keyword, "error": None}
    try:
        vector, tokens = embed(q.strip())
    except ProviderError:
        refund(account_id, estimate)
        keyword = words()
        keyword["ai_status"] = "provider_error"
        return {"data": keyword, "error": None}
    except Exception:
        refund(account_id, estimate)
        raise
    settle(account_id, estimate, tokens)
    filter_params = (account_id, kind, kind, domain, domain, date_from, date_from,
                     date_to, date_to, project_id, project_id, tag_id, tag_id,
                     collection_id, collection_id)
    with connection() as db:
        semantic = db.execute(f"""SELECT {', '.join('m.' + field.strip() for field in FIELDS.split(','))},
            1 - (e.embedding <=> %s::vector) AS semantic_score,
            coalesce(nullif(m.user_note, ''), left(c.body, 240), m.title) AS snippet,
            p.page_number
            FROM memory_embeddings e JOIN memories m ON m.id = e.memory_id AND m.account_id = e.account_id
            JOIN ai_embedding_jobs j ON j.memory_id = e.memory_id AND j.account_id = e.account_id AND j.status = 'ready'
            LEFT JOIN LATERAL (SELECT id, body FROM memory_contents WHERE memory_id = m.id
                AND account_id = m.account_id AND is_active AND provenance IN ('user', 'source', 'extracted')
                ORDER BY version DESC LIMIT 1) c ON true
            LEFT JOIN LATERAL (SELECT page_number FROM content_passages WHERE content_id = c.id
                AND account_id = m.account_id ORDER BY ordinal LIMIT 1) p ON true
            WHERE e.account_id = %s AND e.model = %s AND {_FILTERS}
            ORDER BY e.embedding <=> %s::vector, m.id LIMIT 100""",
            ("[" + ",".join(str(value) for value in vector) + "]", account_id, EMBEDDING_MODEL,
             *filter_params, "[" + ",".join(str(value) for value in vector) + "]")).fetchall()
    ranked = {}
    for rank, row in enumerate(keyword["items"]):
        ranked[str(row["id"])] = (dict(row), 1 / (60 + rank + 1))
    for rank, row in enumerate(semantic):
        key = str(row["id"])
        value, score = ranked.get(key, (dict(row), 0.0))
        similarity = float(row["semantic_score"])
        if key not in ranked:
            value["match_reasons"] = ["semantic"]
            value["score"] = similarity
        else:
            value["match_reasons"] = list(value.get("match_reasons") or []) + ["semantic"]
            if not value.get("snippet"):
                value["snippet"] = row["snippet"]
                value["page_number"] = row["page_number"]
        value["semantic_score"] = similarity
        ranked[key] = (value, score + 1 / (60 + rank + 1))
    ordered = sorted(ranked.values(), key=lambda pair: (-pair[1], -pair[0]["captured_at"].timestamp(), str(pair[0]["id"])))
    rows = [row | {"hybrid_score": score} for row, score in ordered[offset:offset + limit]]
    return {"data": {"items": rows, "total": max(keyword["total"], len(ordered)),
                     "limit": limit, "offset": offset, "match_mode": "hybrid",
                     "ai_status": "ready", "low_confidence": bool(semantic and semantic[0]["semantic_score"] < 0.55)},
            "error": None}
