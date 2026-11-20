"""Account-scoped relationships, graph, timeline, project views, and annotations."""

import hashlib
import uuid
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from .auth import current_session, write_session
from .database import connection
from .memories import FIELDS

router = APIRouter(prefix="/v1", tags=["exploration"])
RelationType = Literal["related", "supports", "contradicts", "inspired_by", "references"]
MemoryKind = Literal["all", "note", "link", "document", "web_page", "snippet", "image", "pdf"]
RELATION_FIELDS = "r.id, r.from_memory_id, r.to_memory_id, r.relation_type, r.explanation, r.provenance, r.created_at, r.updated_at, a.title AS from_title, b.title AS to_title, a.kind AS from_kind, b.kind AS to_kind"
RELATION_JOINS = " FROM memory_relationships r JOIN memories a ON a.id = r.from_memory_id AND a.account_id = r.account_id JOIN memories b ON b.id = r.to_memory_id AND b.account_id = r.account_id "
ANNOTATION_FIELDS = "id, memory_id, content_id, location_kind, source_sha256, start_offset, end_offset, quote, page_number, note, created_at, updated_at"


class RelationshipCreate(BaseModel):
    from_memory_id: uuid.UUID
    to_memory_id: uuid.UUID
    relation_type: RelationType
    explanation: str = Field(min_length=1, max_length=2000)


class RelationshipPatch(BaseModel):
    relation_type: RelationType | None = None
    explanation: str | None = Field(default=None, min_length=1, max_length=2000)


class AnnotationCreate(BaseModel):
    location_kind: Literal["note", "content"]
    quote: str = Field(min_length=1, max_length=2000)
    start_offset: int = Field(ge=0)
    end_offset: int = Field(gt=0)
    page_number: int | None = Field(default=None, gt=0)
    note: str = Field(default="", max_length=2000)


class AnnotationPatch(BaseModel):
    note: str = Field(max_length=2000)


def owned_project(db, account_id, project_id):
    if project_id is None:
        return None
    row = db.execute("SELECT id, name FROM projects WHERE id = %s AND account_id = %s",
                     (project_id, account_id)).fetchone()
    if row is None:
        raise HTTPException(404, detail="Project not found")
    return row


def relationship_row(db, account_id, relation_id):
    return db.execute(f"SELECT {RELATION_FIELDS}{RELATION_JOINS} WHERE r.id = %s AND r.account_id = %s",
                      (relation_id, account_id)).fetchone()


@router.post("/relationships", status_code=201)
def create_relationship(payload: RelationshipCreate, session: dict = Depends(write_session)) -> dict:
    if payload.from_memory_id == payload.to_memory_id:
        raise HTTPException(422, detail="A memory cannot connect to itself")
    explanation = payload.explanation.strip()
    if not explanation:
        raise HTTPException(422, detail="Explain this connection")
    account_id = session["account_id"]
    with connection() as db:
        owned = db.execute("SELECT id FROM memories WHERE account_id = %s AND id = ANY(%s)",
                           (account_id, [payload.from_memory_id, payload.to_memory_id])).fetchall()
        if len(owned) != 2:
            raise HTTPException(404, detail="Memory not found")
        relation_id = uuid.uuid4()
        db.execute("""INSERT INTO memory_relationships
            (id, account_id, from_memory_id, to_memory_id, relation_type, explanation)
            VALUES (%s, %s, %s, %s, %s, %s)""",
            (relation_id, account_id, payload.from_memory_id, payload.to_memory_id,
             payload.relation_type, explanation))
        row = relationship_row(db, account_id, relation_id)
    return {"data": row, "error": None}


@router.get("/relationships")
def list_relationships(session: dict = Depends(current_session), memory_id: uuid.UUID | None = None,
                       project_id: uuid.UUID | None = None,
                       limit: int = Query(default=100, ge=1, le=200),
                       offset: int = Query(default=0, ge=0)) -> dict:
    account_id = session["account_id"]
    predicate = "r.account_id = %s AND (%s::uuid IS NULL OR r.from_memory_id = %s::uuid OR r.to_memory_id = %s::uuid)"
    params = (account_id, memory_id, memory_id, memory_id)
    if project_id:
        predicate += " AND EXISTS (SELECT 1 FROM memory_projects mp WHERE mp.account_id = r.account_id AND mp.project_id = %s AND mp.memory_id IN (r.from_memory_id, r.to_memory_id))"
        params += (project_id,)
    with connection() as db:
        owned_project(db, account_id, project_id)
        total = db.execute(f"SELECT count(*) AS total FROM memory_relationships r WHERE {predicate}",
                           params).fetchone()["total"]
        rows = db.execute(f"SELECT {RELATION_FIELDS}{RELATION_JOINS} WHERE {predicate} "
                          "ORDER BY r.created_at DESC, r.id DESC LIMIT %s OFFSET %s",
                          (*params, limit, offset)).fetchall()
    return {"data": {"items": rows, "total": total, "limit": limit, "offset": offset}, "error": None}


@router.patch("/relationships/{relation_id}")
def update_relationship(relation_id: uuid.UUID, payload: RelationshipPatch,
                        session: dict = Depends(write_session)) -> dict:
    if not payload.model_fields_set:
        raise HTTPException(422, detail="No changes supplied")
    explanation = payload.explanation.strip() if payload.explanation is not None else None
    if payload.explanation is not None and not explanation:
        raise HTTPException(422, detail="Explain this connection")
    with connection() as db:
        updated = db.execute("""UPDATE memory_relationships SET relation_type = COALESCE(%s, relation_type),
            explanation = COALESCE(%s, explanation), updated_at = now()
            WHERE id = %s AND account_id = %s RETURNING id""",
            (payload.relation_type, explanation, relation_id, session["account_id"])).fetchone()
        if updated is None:
            raise HTTPException(404, detail="Relationship not found")
        row = relationship_row(db, session["account_id"], relation_id)
    return {"data": row, "error": None}


@router.delete("/relationships/{relation_id}")
def delete_relationship(relation_id: uuid.UUID, session: dict = Depends(write_session)) -> dict:
    with connection() as db:
        row = db.execute("DELETE FROM memory_relationships WHERE id = %s AND account_id = %s RETURNING id",
                         (relation_id, session["account_id"])).fetchone()
    if row is None:
        raise HTTPException(404, detail="Relationship not found")
    return {"data": {"deleted": True}, "error": None}


@router.get("/relationships/graph")
def graph(session: dict = Depends(current_session), project_id: uuid.UUID | None = None,
          limit: int = Query(default=100, ge=1, le=200)) -> dict:
    account_id = session["account_id"]
    with connection() as db:
        owned_project(db, account_id, project_id)
        predicate = "r.account_id = %s"
        params = (account_id,)
        if project_id:
            predicate += " AND EXISTS (SELECT 1 FROM memory_projects mp WHERE mp.account_id = r.account_id AND mp.project_id = %s AND mp.memory_id IN (r.from_memory_id, r.to_memory_id))"
            params += (project_id,)
        edges = db.execute(f"SELECT {RELATION_FIELDS}{RELATION_JOINS} WHERE {predicate} "
                           "ORDER BY r.created_at DESC, r.id DESC LIMIT %s",
                           (*params, limit + 1)).fetchall()
    truncated = len(edges) > limit
    edges = edges[:limit]
    nodes = {}
    for edge in edges:
        nodes[str(edge["from_memory_id"])] = {"id": edge["from_memory_id"],
              "title": edge["from_title"], "kind": edge["from_kind"]}
        nodes[str(edge["to_memory_id"])] = {"id": edge["to_memory_id"],
              "title": edge["to_title"], "kind": edge["to_kind"]}
    return {"data": {"nodes": list(nodes.values()), "edges": edges, "truncated": truncated}, "error": None}


@router.get("/timeline")
def timeline(session: dict = Depends(current_session), kind: MemoryKind = "all",
             date_from: date | None = None, date_to: date | None = None,
             project_id: uuid.UUID | None = None,
             limit: int = Query(default=50, ge=1, le=100),
             offset: int = Query(default=0, ge=0)) -> dict:
    account_id = session["account_id"]
    predicate = """m.account_id = %s AND (%s = 'all' OR m.kind = %s)
        AND (%s::date IS NULL OR m.captured_at >= %s::date)
        AND (%s::date IS NULL OR m.captured_at < %s::date + interval '1 day')
        AND (%s::uuid IS NULL OR EXISTS (SELECT 1 FROM memory_projects mp
            WHERE mp.account_id = m.account_id AND mp.memory_id = m.id AND mp.project_id = %s::uuid))"""
    params = (account_id, kind, kind, date_from, date_from, date_to, date_to, project_id, project_id)
    with connection() as db:
        owned_project(db, account_id, project_id)
        total = db.execute(f"SELECT count(*) AS total FROM memories m WHERE {predicate}", params).fetchone()["total"]
        rows = db.execute(f"SELECT {', '.join('m.' + field.strip() for field in FIELDS.split(','))} "
                          f"FROM memories m WHERE {predicate} ORDER BY m.captured_at DESC, m.id DESC LIMIT %s OFFSET %s",
                          (*params, limit, offset)).fetchall()
    return {"data": {"items": rows, "total": total, "limit": limit, "offset": offset}, "error": None}


@router.get("/projects/{project_id}/overview")
def project_overview(project_id: uuid.UUID, session: dict = Depends(current_session)) -> dict:
    account_id = session["account_id"]
    with connection() as db:
        project = owned_project(db, account_id, project_id)
        count = db.execute("SELECT count(*) AS total FROM memory_projects WHERE account_id = %s AND project_id = %s",
                           (account_id, project_id)).fetchone()["total"]
        relations = db.execute("""SELECT count(*) AS total FROM memory_relationships r WHERE r.account_id = %s
            AND EXISTS (SELECT 1 FROM memory_projects mp WHERE mp.account_id = r.account_id
                AND mp.project_id = %s AND mp.memory_id IN (r.from_memory_id, r.to_memory_id))""",
            (account_id, project_id)).fetchone()["total"]
        recent = db.execute(f"""SELECT {', '.join('m.' + field.strip() for field in FIELDS.split(','))}
            FROM memories m JOIN memory_projects mp ON mp.memory_id = m.id AND mp.account_id = m.account_id
            WHERE mp.account_id = %s AND mp.project_id = %s
            ORDER BY m.captured_at DESC, m.id DESC LIMIT 20""", (account_id, project_id)).fetchall()
    return {"data": {"project": project, "memory_count": count,
                     "connection_count": relations, "recent_memories": recent}, "error": None}


def annotation_current(db, row, account_id) -> bool:
    if row["location_kind"] == "note":
        source = db.execute("SELECT user_note FROM memories WHERE id = %s AND account_id = %s",
                            (row["memory_id"], account_id)).fetchone()
        return bool(source and hashlib.sha256(source["user_note"].encode()).hexdigest() == row["source_sha256"])
    source = db.execute("SELECT is_active, content_sha256 FROM memory_contents WHERE id = %s AND account_id = %s",
                        (row["content_id"], account_id)).fetchone()
    return bool(source and source["is_active"] and source["content_sha256"] == row["source_sha256"])


@router.get("/memories/{memory_id}/annotations")
def list_annotations(memory_id: uuid.UUID, session: dict = Depends(current_session)) -> dict:
    account_id = session["account_id"]
    with connection() as db:
        owned = db.execute("SELECT 1 FROM memories WHERE id = %s AND account_id = %s",
                           (memory_id, account_id)).fetchone()
        if owned is None:
            raise HTTPException(404, detail="Memory not found")
        rows = db.execute(f"SELECT {ANNOTATION_FIELDS} FROM memory_annotations WHERE memory_id = %s "
                          "AND account_id = %s ORDER BY created_at DESC, id DESC",
                          (memory_id, account_id)).fetchall()
        for row in rows:
            row["current"] = annotation_current(db, row, account_id)
    return {"data": {"items": rows}, "error": None}


@router.post("/memories/{memory_id}/annotations", status_code=201)
def create_annotation(memory_id: uuid.UUID, payload: AnnotationCreate,
                      session: dict = Depends(write_session)) -> dict:
    account_id = session["account_id"]
    with connection() as db:
        memory = db.execute("SELECT user_note FROM memories WHERE id = %s AND account_id = %s",
                            (memory_id, account_id)).fetchone()
        if memory is None:
            raise HTTPException(404, detail="Memory not found")
        content_id = None
        if payload.location_kind == "note":
            if payload.page_number is not None:
                raise HTTPException(422, detail="Notes do not have page numbers")
            body = memory["user_note"]
        else:
            content = db.execute("""SELECT id, body FROM memory_contents WHERE memory_id = %s AND account_id = %s
                AND is_active AND provenance IN ('user', 'source', 'extracted')
                ORDER BY version DESC LIMIT 1""", (memory_id, account_id)).fetchone()
            if content is None:
                raise HTTPException(409, detail="No active saved text is available to annotate")
            content_id, body = content["id"], content["body"]
            if payload.page_number is not None:
                passage = db.execute("""SELECT start_offset, end_offset FROM content_passages WHERE
                    content_id = %s AND memory_id = %s AND account_id = %s AND page_number = %s""",
                    (content_id, memory_id, account_id, payload.page_number)).fetchone()
                if passage is None or passage["start_offset"] is None or not (
                    passage["start_offset"] <= payload.start_offset < payload.end_offset <= passage["end_offset"]
                ):
                    raise HTTPException(422, detail="Highlight must be within the selected PDF page")
        if (payload.end_offset > len(body) or body[payload.start_offset:payload.end_offset] != payload.quote):
            raise HTTPException(422, detail="Highlighted quote does not match this saved text location")
        annotation_id = uuid.uuid4()
        row = db.execute(f"""INSERT INTO memory_annotations
            (id, account_id, memory_id, content_id, location_kind, source_sha256,
             start_offset, end_offset, quote, page_number, note)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING {ANNOTATION_FIELDS}""",
            (annotation_id, account_id, memory_id, content_id, payload.location_kind,
             hashlib.sha256(body.encode()).hexdigest(), payload.start_offset, payload.end_offset,
             payload.quote, payload.page_number, payload.note)).fetchone()
        row["current"] = True
    return {"data": row, "error": None}


@router.patch("/annotations/{annotation_id}")
def update_annotation(annotation_id: uuid.UUID, payload: AnnotationPatch,
                      session: dict = Depends(write_session)) -> dict:
    with connection() as db:
        row = db.execute(f"""UPDATE memory_annotations SET note = %s, updated_at = now()
            WHERE id = %s AND account_id = %s RETURNING {ANNOTATION_FIELDS}""",
            (payload.note, annotation_id, session["account_id"])).fetchone()
        if row is None:
            raise HTTPException(404, detail="Annotation not found")
        row["current"] = annotation_current(db, row, session["account_id"])
    return {"data": row, "error": None}


@router.delete("/annotations/{annotation_id}")
def delete_annotation(annotation_id: uuid.UUID, session: dict = Depends(write_session)) -> dict:
    with connection() as db:
        row = db.execute("DELETE FROM memory_annotations WHERE id = %s AND account_id = %s RETURNING id",
                         (annotation_id, session["account_id"])).fetchone()
    if row is None:
        raise HTTPException(404, detail="Annotation not found")
    return {"data": {"deleted": True}, "error": None}
