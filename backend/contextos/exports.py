"""Private account export of source records, content, and originals."""

import json
import hashlib
import uuid
from datetime import datetime, timezone
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from fastapi import APIRouter, BackgroundTasks, Depends
from fastapi.responses import FileResponse

from .auth import current_session
from .database import connection
from .storage import path_for

router = APIRouter(prefix="/v1", tags=["export"])
EXPORT_ROOT = Path(__file__).resolve().parents[2] / "data" / "exports"


def write_jsonl(archive: ZipFile, name: str, records: list[dict]) -> None:
    body = "".join(json.dumps(row, default=str, ensure_ascii=False, separators=(",", ":")) + "\n"
                   for row in records)
    archive.writestr(name, body.encode("utf-8"))


@router.get("/export")
def export_account(background_tasks: BackgroundTasks, session: dict = Depends(current_session)):
    account_id = session["account_id"]
    with connection() as db:
        db.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        memories = db.execute(
            "SELECT id, kind, title, source_uri, source_domain, captured_at, published_at, "
            "status, user_note, capture_reason, capture_method, source_author, source_image_uri, created_at, updated_at FROM memories WHERE account_id = %s ORDER BY id",
            (account_id,),
        ).fetchall()
        contents = db.execute(
            "SELECT id, memory_id, version, provenance, body, content_sha256, processor_version, "
            "status, is_active, created_at FROM memory_contents WHERE account_id = %s "
            "ORDER BY memory_id, provenance, version", (account_id,),
        ).fetchall()
        passages = db.execute("""SELECT id, memory_id, content_id, ordinal, body, page_number,
            section_label, start_offset, end_offset FROM content_passages WHERE account_id = %s
            ORDER BY memory_id, content_id, ordinal""", (account_id,)).fetchall()
        assets = db.execute(
            "SELECT id, memory_id, role, object_key, mime_type, byte_size, sha256, "
            "source_filename, created_at FROM memory_assets "
            "WHERE account_id = %s AND storage_state = 'stored' ORDER BY memory_id, id",
            (account_id,),
        ).fetchall()
        projects = db.execute(
            "SELECT id, name, created_at FROM projects WHERE account_id = %s ORDER BY id",
            (account_id,),
        ).fetchall()
        assignments = db.execute(
            "SELECT memory_id, project_id FROM memory_projects WHERE account_id = %s ORDER BY memory_id, project_id",
            (account_id,),
        ).fetchall()
        collections = db.execute(
            "SELECT id, name, created_at FROM collections WHERE account_id = %s ORDER BY id", (account_id,),
        ).fetchall()
        collection_assignments = db.execute(
            "SELECT memory_id, collection_id FROM collection_memories WHERE account_id = %s ORDER BY memory_id, collection_id",
            (account_id,),
        ).fetchall()
        tags = db.execute(
            "SELECT id, name, created_at FROM tags WHERE account_id = %s ORDER BY id", (account_id,),
        ).fetchall()
        tag_assignments = db.execute(
            "SELECT memory_id, tag_id FROM memory_tags WHERE account_id = %s ORDER BY memory_id, tag_id",
            (account_id,),
        ).fetchall()

    EXPORT_ROOT.mkdir(parents=True, exist_ok=True)
    output = EXPORT_ROOT / f"{uuid.uuid4()}.zip"
    try:
        exported_assets = []
        with ZipFile(output, "x", compression=ZIP_DEFLATED, compresslevel=6) as archive:
            write_jsonl(archive, "memories.jsonl", memories)
            write_jsonl(archive, "contents.jsonl", contents)
            write_jsonl(archive, "passages.jsonl", passages)
            write_jsonl(archive, "projects.jsonl", projects)
            write_jsonl(archive, "memory_projects.jsonl", assignments)
            write_jsonl(archive, "collections.jsonl", collections)
            write_jsonl(archive, "collection_memories.jsonl", collection_assignments)
            write_jsonl(archive, "tags.jsonl", tags)
            write_jsonl(archive, "memory_tags.jsonl", tag_assignments)
            for asset in assets:
                source = path_for(asset["object_key"])
                archive_path = f"originals/{asset['id']}"
                original = source.read_bytes()
                if hashlib.sha256(original).hexdigest() != asset["sha256"]:
                    raise ValueError("An original asset failed its checksum check")
                archive.writestr(archive_path, original)
                exported_assets.append({
                    key: value for key, value in asset.items() if key != "object_key"
                } | {"path": archive_path})
            write_jsonl(archive, "assets.jsonl", exported_assets)
            archive.writestr("manifest.json", json.dumps({
                "format": "contextos-account-export", "version": 2,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "memory_count": len(memories), "content_count": len(contents),
                "passage_count": len(passages),
                "asset_count": len(exported_assets),
                "project_count": len(projects), "assignment_count": len(assignments),
                "collection_count": len(collections), "collection_assignment_count": len(collection_assignments),
                "tag_count": len(tags), "tag_assignment_count": len(tag_assignments),
            }, indent=2).encode("utf-8"))
    except BaseException:
        output.unlink(missing_ok=True)
        raise
    background_tasks.add_task(output.unlink, missing_ok=True)
    return FileResponse(output, filename="contextos-export.zip", media_type="application/zip",
                        background=background_tasks)
