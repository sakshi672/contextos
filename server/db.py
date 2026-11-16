"""Local development persistence for the first Context OS vertical slice."""

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path(os.environ.get("CONTEXT_OS_DB", Path(__file__).resolve().parents[1] / "data" / "context.db"))


@contextmanager
def connection():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    try:
        yield db
        db.commit()
    finally:
        db.close()


def initialize():
    with connection() as db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS memories (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                kind TEXT NOT NULL CHECK(kind IN ('note', 'link')),
                source_url TEXT,
                note TEXT NOT NULL DEFAULT '',
                captured_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE VIRTUAL TABLE IF NOT EXISTS memory_search USING fts5(
                id UNINDEXED, title, note, source_url
            );
        """)


def row_to_memory(row):
    return dict(row) if row else None
