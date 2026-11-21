"""Reviewable similarity suggestions; never changes organization automatically."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from .ai_provider import EMBEDDING_MODEL
from .auth import current_session, write_session
from .database import connection

router = APIRouter(prefix="/v1/ai", tags=["ai"])


class Review(BaseModel):
    decision: str


def _enabled(db, account_id):
    row = db.execute("SELECT enabled FROM ai_preferences WHERE account_id = %s", (account_id,)).fetchone()
    if not row or not row["enabled"]:
        raise HTTPException(403, detail="AI is disabled for this account")


def _candidate(db, account_id, memory_id, related_id, project_id, kind, similarity):
    if similarity < 0.65:
        return
    existing = db.execute("""SELECT 1 FROM ai_suggestions WHERE account_id = %s AND kind = %s
        AND memory_id = %s AND related_memory_id IS NOT DISTINCT FROM %s::uuid
        AND project_id IS NOT DISTINCT FROM %s::uuid""",
        (account_id, kind, memory_id, related_id, project_id)).fetchone()
    if existing:
        return
    memory = db.execute("SELECT title FROM memories WHERE id = %s AND account_id = %s", (memory_id, account_id)).fetchone()
    related = db.execute("SELECT title FROM memories WHERE id = %s AND account_id = %s", (related_id, account_id)).fetchone()
    if not memory or not related:
        return
    evidence = f"Similar saved text ({similarity:.0%} similarity): {memory['title']} / {related['title']}. Review both sources before accepting."
    db.execute("""INSERT INTO ai_suggestions(id, account_id, kind, memory_id, related_memory_id,
        project_id, evidence, model) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
        (uuid.uuid4(), account_id, kind, memory_id, related_id, project_id, evidence[:1000], EMBEDDING_MODEL))


@router.post("/suggestions/refresh")
def refresh_suggestions(session: dict = Depends(write_session), memory_id: uuid.UUID | None = None,
                        project_id: uuid.UUID | None = None) -> dict:
    if (memory_id is None) == (project_id is None):
        raise HTTPException(422, detail="Select one memory or project")
    account_id = session["account_id"]
    with connection() as db:
        _enabled(db, account_id)
        if memory_id:
            owned = db.execute("SELECT 1 FROM memories WHERE id = %s AND account_id = %s", (memory_id, account_id)).fetchone()
            if not owned:
                raise HTTPException(404, detail="Memory not found")
            matches = db.execute("""SELECT b.memory_id, 1 - (b.embedding <=> a.embedding) AS similarity
                FROM memory_embeddings a JOIN memory_embeddings b ON b.account_id = a.account_id
                  AND b.model = a.model AND b.memory_id <> a.memory_id
                WHERE a.account_id = %s AND a.memory_id = %s AND a.model = %s
                ORDER BY b.embedding <=> a.embedding, b.memory_id LIMIT 10""",
                (account_id, memory_id, EMBEDDING_MODEL)).fetchall()
            for match in matches:
                _candidate(db, account_id, memory_id, match["memory_id"], None, "related", float(match["similarity"]))
        else:
            owned = db.execute("SELECT 1 FROM projects WHERE id = %s AND account_id = %s", (project_id, account_id)).fetchone()
            if not owned:
                raise HTTPException(404, detail="Project not found")
            matches = db.execute("""SELECT candidate.memory_id, member.memory_id AS example_id,
                1 - (candidate.embedding <=> member.embedding) AS similarity
                FROM memory_projects mp JOIN memory_embeddings member ON member.memory_id = mp.memory_id
                  AND member.account_id = mp.account_id AND member.model = %s
                JOIN memory_embeddings candidate ON candidate.account_id = member.account_id
                  AND candidate.model = member.model AND candidate.memory_id <> member.memory_id
                WHERE mp.account_id = %s AND mp.project_id = %s
                  AND NOT EXISTS (SELECT 1 FROM memory_projects assigned WHERE assigned.account_id = mp.account_id
                    AND assigned.project_id = mp.project_id AND assigned.memory_id = candidate.memory_id)
                ORDER BY similarity DESC, candidate.memory_id LIMIT 20""",
                (EMBEDDING_MODEL, account_id, project_id)).fetchall()
            for match in matches:
                _candidate(db, account_id, match["memory_id"], match["example_id"], project_id,
                           "project", float(match["similarity"]))
        count = db.execute("""SELECT count(*) AS n FROM ai_suggestions WHERE account_id = %s
            AND status = 'pending' AND (%s::uuid IS NULL OR memory_id = %s::uuid)
            AND (%s::uuid IS NULL OR project_id = %s::uuid)""",
            (account_id, memory_id, memory_id, project_id, project_id)).fetchone()["n"]
    return {"data": {"pending": count}, "error": None}


@router.get("/suggestions")
def list_suggestions(session: dict = Depends(current_session), memory_id: uuid.UUID | None = None,
                     project_id: uuid.UUID | None = None, status: str = Query(default="pending")) -> dict:
    if status not in ("pending", "approved", "dismissed"):
        raise HTTPException(422, detail="Invalid status")
    account_id = session["account_id"]
    with connection() as db:
        _enabled(db, account_id)
        rows = db.execute("""SELECT s.id, s.kind, s.memory_id, s.related_memory_id, s.project_id,
            s.evidence, s.status, s.created_at, a.title AS memory_title, b.title AS related_title
            FROM ai_suggestions s JOIN memories a ON a.id = s.memory_id AND a.account_id = s.account_id
            LEFT JOIN memories b ON b.id = s.related_memory_id AND b.account_id = s.account_id
            WHERE s.account_id = %s AND s.status = %s
              AND (%s::uuid IS NULL OR s.memory_id = %s::uuid OR s.related_memory_id = %s::uuid)
              AND (%s::uuid IS NULL OR s.project_id = %s::uuid)
            ORDER BY s.created_at DESC LIMIT 50""",
            (account_id, status, memory_id, memory_id, memory_id, project_id, project_id)).fetchall()
    return {"data": {"items": rows}, "error": None}


@router.post("/suggestions/{suggestion_id}/review")
def review_suggestion(suggestion_id: uuid.UUID, payload: Review,
                      session: dict = Depends(write_session)) -> dict:
    if payload.decision not in ("approve", "dismiss"):
        raise HTTPException(422, detail="Choose approve or dismiss")
    account_id = session["account_id"]
    with connection() as db:
        _enabled(db, account_id)
        item = db.execute("SELECT * FROM ai_suggestions WHERE id = %s AND account_id = %s FOR UPDATE",
                          (suggestion_id, account_id)).fetchone()
        if not item:
            raise HTTPException(404, detail="Suggestion not found")
        if item["status"] != "pending":
            raise HTTPException(409, detail="Suggestion already reviewed")
        if payload.decision == "approve":
            if item["kind"] == "related":
                db.execute("""INSERT INTO memory_relationships(id, account_id, from_memory_id,
                    to_memory_id, relation_type, explanation) VALUES (%s, %s, %s, %s, 'related', %s)""",
                    (uuid.uuid4(), account_id, item["memory_id"], item["related_memory_id"], item["evidence"]))
            elif item["kind"] == "project":
                db.execute("""INSERT INTO memory_projects(account_id, memory_id, project_id)
                    VALUES (%s, %s, %s) ON CONFLICT DO NOTHING""",
                    (account_id, item["memory_id"], item["project_id"]))
            else:
                raise HTTPException(422, detail="This suggestion cannot be approved")
        db.execute("UPDATE ai_suggestions SET status = %s, reviewed_at = now() WHERE id = %s",
                   ("approved" if payload.decision == "approve" else "dismissed", suggestion_id))
    return {"data": {"status": "approved" if payload.decision == "approve" else "dismissed"}, "error": None}
