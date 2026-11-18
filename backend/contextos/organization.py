"""Account-owned projects, tags, collections, and many-to-many assignments."""

import uuid
from typing import Literal

import psycopg
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .auth import current_session, write_session
from .database import connection

router = APIRouter(prefix="/v1/organization", tags=["organization"])
Entity = Literal["projects", "collections", "tags"]
TABLES = {
    "projects": ("projects", "memory_projects", "project_id", 120),
    "collections": ("collections", "collection_memories", "collection_id", 120),
    "tags": ("tags", "memory_tags", "tag_id", 80),
}


class NameInput(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class Assignments(BaseModel):
    project_ids: list[uuid.UUID] = Field(default_factory=list, max_length=100)
    collection_ids: list[uuid.UUID] = Field(default_factory=list, max_length=100)
    tag_ids: list[uuid.UUID] = Field(default_factory=list, max_length=100)


def cleaned_name(value: str, maximum: int) -> str:
    name = value.strip()
    if not name or len(name) > maximum:
        raise HTTPException(422, detail=f"Name must be 1–{maximum} characters")
    return name


def assignments_for(db, account_id, memory_id) -> dict:
    result = {}
    for entity, (table, join_table, foreign_key, _) in TABLES.items():
        result[entity] = db.execute(
            f"SELECT t.id, t.name FROM {join_table} j JOIN {table} t ON t.id = j.{foreign_key} "
            "WHERE j.account_id = %s AND j.memory_id = %s ORDER BY lower(t.name), t.id",
            (account_id, memory_id),
        ).fetchall()
    return result


@router.get("")
def list_organization(session: dict = Depends(current_session)) -> dict:
    account_id = session["account_id"]
    result = {}
    with connection() as db:
        for entity, (table, join_table, foreign_key, _) in TABLES.items():
            result[entity] = db.execute(
                f"SELECT t.id, t.name, count(j.memory_id) AS memory_count FROM {table} t "
                f"LEFT JOIN {join_table} j ON j.{foreign_key} = t.id AND j.account_id = t.account_id "
                "WHERE t.account_id = %s GROUP BY t.id ORDER BY lower(t.name), t.id",
                (account_id,),
            ).fetchall()
    return {"data": result, "error": None}


@router.post("/{entity}", status_code=201)
def create_entity(entity: Entity, payload: NameInput, session: dict = Depends(write_session)) -> dict:
    table, _, _, maximum = TABLES[entity]
    name = cleaned_name(payload.name, maximum)
    try:
        with connection() as db:
            row = db.execute(
                f"INSERT INTO {table} (id, account_id, name) VALUES (%s, %s, %s) RETURNING id, name",
                (uuid.uuid4(), session["account_id"], name),
            ).fetchone()
    except psycopg.errors.UniqueViolation as exc:
        raise HTTPException(409, detail=f"{entity[:-1].capitalize()} already exists") from exc
    return {"data": row, "error": None}


@router.patch("/{entity}/{entity_id}")
def rename_entity(entity: Entity, entity_id: uuid.UUID, payload: NameInput,
                  session: dict = Depends(write_session)) -> dict:
    table, _, _, maximum = TABLES[entity]
    name = cleaned_name(payload.name, maximum)
    try:
        with connection() as db:
            row = db.execute(
                f"UPDATE {table} SET name = %s WHERE id = %s AND account_id = %s RETURNING id, name",
                (name, entity_id, session["account_id"]),
            ).fetchone()
    except psycopg.errors.UniqueViolation as exc:
        raise HTTPException(409, detail=f"{entity[:-1].capitalize()} already exists") from exc
    if row is None:
        raise HTTPException(404, detail="Organization item not found")
    return {"data": row, "error": None}


@router.delete("/{entity}/{entity_id}")
def delete_entity(entity: Entity, entity_id: uuid.UUID, session: dict = Depends(write_session)) -> dict:
    table, join_table, foreign_key, _ = TABLES[entity]
    with connection() as db:
        owned = db.execute(f"SELECT 1 FROM {table} WHERE id = %s AND account_id = %s FOR UPDATE",
                           (entity_id, session["account_id"])).fetchone()
        if owned is None:
            raise HTTPException(404, detail="Organization item not found")
        db.execute(f"DELETE FROM {join_table} WHERE account_id = %s AND {foreign_key} = %s",
                   (session["account_id"], entity_id))
        db.execute(f"DELETE FROM {table} WHERE id = %s AND account_id = %s",
                   (entity_id, session["account_id"]))
    return {"data": {"deleted": True}, "error": None}


@router.put("/memories/{memory_id}")
def replace_assignments(memory_id: uuid.UUID, payload: Assignments,
                        session: dict = Depends(write_session)) -> dict:
    account_id = session["account_id"]
    requested = {"projects": payload.project_ids, "collections": payload.collection_ids,
                 "tags": payload.tag_ids}
    with connection() as db:
        memory = db.execute("SELECT 1 FROM memories WHERE id = %s AND account_id = %s FOR UPDATE",
                            (memory_id, account_id)).fetchone()
        if memory is None:
            raise HTTPException(404, detail="Memory not found")
        for entity, ids in requested.items():
            if len(ids) != len(set(ids)):
                raise HTTPException(422, detail=f"Duplicate {entity} ID")
            table, _, _, _ = TABLES[entity]
            found = db.execute(f"SELECT id FROM {table} WHERE account_id = %s AND id = ANY(%s)",
                               (account_id, ids)).fetchall()
            if len(found) != len(ids):
                raise HTTPException(422, detail=f"Unknown or unowned {entity} ID")
        for entity, ids in requested.items():
            _, join_table, foreign_key, _ = TABLES[entity]
            db.execute(f"DELETE FROM {join_table} WHERE memory_id = %s AND account_id = %s",
                       (memory_id, account_id))
            for entity_id in ids:
                db.execute(f"INSERT INTO {join_table} (account_id, memory_id, {foreign_key}) VALUES (%s, %s, %s)",
                           (account_id, memory_id, entity_id))
        result = assignments_for(db, account_id, memory_id)
    return {"data": result, "error": None}
