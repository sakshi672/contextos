"""Ranked, account-scoped keyword retrieval across saved memories."""

import uuid
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, Query

from .auth import current_session
from .database import connection
from .memories import FIELDS

router = APIRouter(prefix="/v1/search", tags=["search"])

_CANDIDATES = """
WITH term AS (SELECT websearch_to_tsquery('english'::regconfig, %s) AS words),
candidate AS (
    SELECT m.id FROM memories m CROSS JOIN term
    WHERE m.account_id = %s AND (m.search_document @@ term.words OR m.search_metadata @@ term.words)
    UNION
    SELECT c.memory_id FROM memory_contents c CROSS JOIN term
    WHERE c.account_id = %s AND c.is_active AND c.provenance IN ('user', 'source', 'extracted')
      AND c.search_document @@ term.words
)
"""

_FILTERS = """m.account_id = %s AND (%s = 'all' OR m.kind = %s)
    AND (%s::text IS NULL OR m.source_domain = %s)
    AND (%s::date IS NULL OR m.captured_at >= %s::date)
    AND (%s::date IS NULL OR m.captured_at < %s::date + interval '1 day')
    AND (%s::uuid IS NULL OR EXISTS (
        SELECT 1 FROM memory_projects mp WHERE mp.memory_id = m.id
        AND mp.account_id = m.account_id AND mp.project_id = %s::uuid
    ))"""


@router.get("")
def search_memories(
    q: str = Query(min_length=1, max_length=200),
    session: dict = Depends(current_session),
    kind: Literal["all", "note", "link", "document", "web_page", "snippet", "image", "pdf"] = "all",
    domain: str | None = Query(default=None, max_length=255),
    date_from: date | None = None,
    date_to: date | None = None,
    project_id: uuid.UUID | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict:
    account_id = session["account_id"]
    if not q.strip():
        return {"data": {"items": [], "total": 0, "limit": limit, "offset": offset}, "error": None}
    candidate_params = (q.strip(), account_id, account_id)
    filter_params = (account_id, kind, kind, domain, domain, date_from, date_from,
                     date_to, date_to, project_id, project_id)
    with connection() as db:
        total = db.execute(
            _CANDIDATES + f"SELECT count(*) AS total FROM candidate ids JOIN memories m ON m.id = ids.id WHERE {_FILTERS}",
            (*candidate_params, *filter_params),
        ).fetchone()["total"]
        rows = db.execute(
            _CANDIDATES + f"""
            SELECT {', '.join('m.' + field.strip() for field in FIELDS.split(','))},
                (ts_rank_cd(m.search_document, term.words) * 4 +
                 ts_rank_cd(m.search_metadata, term.words) + coalesce(hit.rank, 0)) AS score,
                array_remove(ARRAY[
                    CASE WHEN to_tsvector('english'::regconfig, m.title) @@ term.words THEN 'title' END,
                    CASE WHEN to_tsvector('english'::regconfig, m.user_note) @@ term.words THEN 'note' END,
                    CASE WHEN m.search_metadata @@ term.words THEN 'source' END,
                    CASE WHEN hit.content_id IS NOT NULL THEN 'content' END
                ], NULL) AS match_reasons,
                hit.snippet, passage.page_number
            FROM candidate ids JOIN memories m ON m.id = ids.id CROSS JOIN term
            LEFT JOIN LATERAL (
                SELECT c.id AS content_id, ts_rank_cd(c.search_document, term.words) AS rank,
                    ts_headline('english'::regconfig, c.body, term.words,
                        'MaxWords=24, MinWords=8, StartSel=[, StopSel=]') AS snippet
                FROM memory_contents c WHERE c.memory_id = m.id AND c.account_id = m.account_id
                    AND c.is_active AND c.provenance IN ('user', 'source', 'extracted')
                    AND c.search_document @@ term.words
                ORDER BY rank DESC, c.version DESC LIMIT 1
            ) hit ON true
            LEFT JOIN LATERAL (
                SELECT p.page_number FROM content_passages p
                WHERE p.content_id = hit.content_id AND p.account_id = m.account_id
                    AND p.search_document @@ term.words
                ORDER BY ts_rank_cd(p.search_document, term.words) DESC, p.ordinal LIMIT 1
            ) passage ON true
            WHERE {_FILTERS}
            ORDER BY score DESC, m.captured_at DESC, m.id DESC LIMIT %s OFFSET %s
            """,
            (*candidate_params, *filter_params, limit, offset),
        ).fetchall()
    return {"data": {"items": rows, "total": total, "limit": limit, "offset": offset}, "error": None}
