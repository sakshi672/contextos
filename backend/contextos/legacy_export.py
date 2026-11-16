"""Read-only snapshot of the local SQLite prototype before account migration."""

import argparse
import hashlib
import json
import sqlite3
from contextlib import closing
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

FIELDS = ("id", "title", "kind", "source_url", "note", "captured_at", "updated_at")


def export_legacy(database_path: Path, output_path: Path) -> int:
    database_path = database_path.resolve(strict=True)
    if not database_path.is_file():
        raise ValueError("The SQLite source must be a file")
    if output_path.exists():
        raise FileExistsError(f"Will not overwrite existing snapshot: {output_path}")

    # mode=ro prevents schema creation or accidental edits to the source.
    with closing(sqlite3.connect(database_path.as_uri() + "?mode=ro", uri=True)) as db:
        db.row_factory = sqlite3.Row
        db.execute("BEGIN")
        columns = {row[1] for row in db.execute("PRAGMA table_info(memories)")}
        if not set(FIELDS).issubset(columns):
            raise ValueError("Source is not the expected Context OS prototype database")
        records = [dict(row) for row in db.execute(
            "SELECT id, title, kind, source_url, note, captured_at, updated_at FROM memories ORDER BY id"
        )]
        db.commit()

    if len(records) != len({record["id"] for record in records}):
        raise ValueError("Duplicate memory IDs in SQLite source")
    jsonl = "".join(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n" for record in records).encode("utf-8")
    manifest = {
        "format": "contextos-legacy-sqlite-snapshot",
        "version": 1,
        "memory_count": len(records),
        "memories_sha256": hashlib.sha256(jsonl).hexdigest(),
        "fields": list(FIELDS),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output_path, "x", compression=ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest, indent=2) + "\n")
        archive.writestr("memories.jsonl", jsonl)
    return len(records)


def main():
    parser = argparse.ArgumentParser(description="Snapshot the local SQLite prototype without modifying it")
    parser.add_argument("database", type=Path, help="Existing data/context.db path")
    parser.add_argument("output", type=Path, help="New .zip snapshot path; must not exist")
    args = parser.parse_args()
    print(f"Exported {export_legacy(args.database, args.output)} memories to {args.output}")


if __name__ == "__main__":
    main()
