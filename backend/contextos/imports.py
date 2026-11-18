"""Import version-one account exports and Netscape browser bookmarks."""

import hashlib
import json
import uuid
from datetime import datetime, timezone
from html.parser import HTMLParser
from io import BytesIO
from pathlib import PurePosixPath
from urllib.parse import urlsplit
from zipfile import BadZipFile, ZipFile

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from .auth import write_session
from .database import connection
from .memories import clean_title, source_domain
from .captures import assign_project
from .storage import delete, object_key, path_for
from .uploads import valid_image

router = APIRouter(prefix="/v1", tags=["import"])
MAX_IMPORT_BYTES = 60 * 1024 * 1024
MAX_EXPANDED_BYTES = 100 * 1024 * 1024
MAX_RECORDS = 5000


class BookmarkParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.items = []
        self.current = None

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "a":
            attributes = dict(attrs)
            self.current = {"source_uri": attributes.get("href", ""),
                            "add_date": attributes.get("add_date"), "title": ""}

    def handle_data(self, data):
        if self.current is not None:
            self.current["title"] += data

    def handle_endtag(self, tag):
        if tag.lower() == "a" and self.current is not None:
            self.items.append(self.current)
            self.current = None


def read_jsonl(archive: ZipFile, name: str) -> list[dict]:
    rows = []
    for line in archive.read(name).decode("utf-8").splitlines():
        if line.strip():
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"Invalid {name} record")
            rows.append(value)
    return rows


def parse_export(raw: bytes):
    try:
        with ZipFile(BytesIO(raw)) as archive:
            infos = archive.infolist()
            if len(infos) > MAX_RECORDS * 2 + 7 or sum(info.file_size for info in infos) > MAX_EXPANDED_BYTES:
                raise ValueError("Export exceeds import limits")
            names = [info.filename for info in infos]
            if len(names) != len(set(names)) or any(
                name.startswith("/") or ".." in PurePosixPath(name).parts for name in names
            ):
                raise ValueError("Unsafe export paths")
            manifest = json.loads(archive.read("manifest.json"))
            if manifest.get("format") != "contextos-account-export" or manifest.get("version") != 1:
                raise ValueError("Unsupported export version")
            memories = read_jsonl(archive, "memories.jsonl")
            contents = read_jsonl(archive, "contents.jsonl")
            passages = read_jsonl(archive, "passages.jsonl") if "passages.jsonl" in names else []
            assets = read_jsonl(archive, "assets.jsonl")
            projects = read_jsonl(archive, "projects.jsonl") if "projects.jsonl" in names else []
            assignments = read_jsonl(archive, "memory_projects.jsonl") if "memory_projects.jsonl" in names else []
            if (len(memories) > MAX_RECORDS or len(contents) > MAX_RECORDS * 5 or
                len(assets) > MAX_RECORDS or len(passages) > MAX_RECORDS * 200 or
                len(projects) > MAX_RECORDS or len(assignments) > MAX_RECORDS or
                any(manifest.get(key) != count for key, count in (
                    ("memory_count", len(memories)), ("content_count", len(contents)),
                    ("asset_count", len(assets))))):
                raise ValueError("Export counts do not match")
            if ("project_count" in manifest and manifest["project_count"] != len(projects)) or (
                "assignment_count" in manifest and manifest["assignment_count"] != len(assignments)):
                raise ValueError("Project counts do not match")
            if "passage_count" in manifest and manifest["passage_count"] != len(passages):
                raise ValueError("Passage counts do not match")
            project_names = {row["id"]: row["name"] for row in projects}
            if len(project_names) != len(projects):
                raise ValueError("Duplicate project ID")
            project_for_memory = {}
            for assignment in assignments:
                project_for_memory.setdefault(assignment["memory_id"], []).append(project_names[assignment["project_id"]])
            if any(len(names) > 1 for names in project_for_memory.values()):
                raise ValueError("Multiple projects per memory are not supported yet")
            originals = {}
            for asset in assets:
                path = asset["path"]
                if path != f"originals/{uuid.UUID(asset['id'])}":
                    raise ValueError("Invalid original path")
                info = archive.getinfo(path)
                limit = (50 * 1024 * 1024 if asset.get("mime_type") == "application/pdf" else
                         20 * 1024 * 1024 if asset.get("role") == "screenshot" or asset.get("mime_type", "").startswith("image/") else
                         10 * 1024 * 1024)
                if info.file_size > limit:
                    raise ValueError("Original exceeds its size limit")
                body = archive.read(path)
                if len(body) != asset["byte_size"] or hashlib.sha256(body).hexdigest() != asset["sha256"]:
                    raise ValueError("Original checksum mismatch")
                originals[asset["id"]] = body
            return memories, contents, passages, assets, originals, project_for_memory
    except (BadZipFile, KeyError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise HTTPException(422, detail=f"Invalid Context OS export: {exc}") from exc


def timestamp(value, default=None):
    if not value:
        return default or datetime.now(timezone.utc)
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Date needs a timezone")
    return parsed


def import_record(account_id, row, contents, passages, assets, originals, project_name=None):
    kind = row["kind"]
    if kind not in {"note", "link", "document", "web_page", "snippet", "image", "pdf"}:
        raise ValueError("Unsupported memory type")
    title = clean_title(row["title"])
    if len(title) > 240:
        raise ValueError("Title too long")
    note = row.get("user_note") or ""
    if len(note) > 20000:
        raise ValueError("Note too long")
    uri = row.get("source_uri")
    domain = source_domain(kind, uri) if kind in {"note", "link", "web_page", "snippet"} else None
    if kind in {"document", "image", "pdf"} and uri:
        raise ValueError("Uploaded files cannot have a source URL")
    if kind in {"document", "image", "pdf"} and (len(assets) != 1 or assets[0]["role"] != "original"):
        raise ValueError("Uploaded file needs one original")
    if kind == "pdf" and (assets[0]["mime_type"] != "application/pdf" or
                           not originals[assets[0]["id"]].startswith(b"%PDF-")):
        raise ValueError("Invalid PDF original")
    if kind == "image":
        mime_type = assets[0]["mime_type"]
        if mime_type not in {"image/png", "image/jpeg", "image/webp"} or not valid_image(originals[assets[0]["id"]], mime_type):
            raise ValueError("Invalid image original")
    if kind == "web_page" and (len(assets) > 1 or any(asset["role"] != "screenshot" for asset in assets)):
        raise ValueError("Web page assets must be a single screenshot")
    if kind in {"note", "link", "snippet"} and assets:
        raise ValueError("This memory type cannot include files")
    if kind == "snippet":
        active = [content for content in contents if content.get("provenance") == "user" and content.get("is_active")]
        if (len(active) != 1 or not isinstance(active[0].get("body"), str) or
            not active[0]["body"].strip() or len(active[0]["body"].encode("utf-8")) > 2 * 1024 * 1024):
            raise ValueError("Snippet needs one active pasted text version under 2 MiB")
    memory_id = uuid.uuid4()
    keys = []
    try:
        with connection() as db:
            if kind == "link":
                duplicate = db.execute("SELECT id FROM memories WHERE account_id = %s AND kind = 'link' AND source_uri = %s LIMIT 1",
                                       (account_id, uri)).fetchone()
            elif kind == "note":
                duplicate = db.execute("SELECT id FROM memories WHERE account_id = %s AND kind = 'note' AND title = %s AND user_note = %s LIMIT 1",
                                       (account_id, title, note)).fetchone()
            elif kind == "snippet":
                active_hash = next(content["content_sha256"] for content in contents
                                   if content.get("provenance") == "user" and content.get("is_active"))
                duplicate = db.execute("""SELECT m.id FROM memories m JOIN memory_contents c ON c.memory_id = m.id
                    WHERE m.account_id = %s AND m.kind = 'snippet' AND m.title = %s AND m.user_note = %s
                    AND c.provenance = 'user' AND c.is_active AND c.content_sha256 = %s LIMIT 1""",
                    (account_id, title, note, active_hash)).fetchone()
            elif kind in {"document", "image", "pdf"}:
                duplicate = db.execute("""SELECT m.id FROM memories m JOIN memory_assets a ON a.memory_id = m.id
                    WHERE m.account_id = %s AND m.kind = %s AND a.sha256 = %s LIMIT 1""",
                    (account_id, kind, assets[0]["sha256"])).fetchone()
            else:
                source_content = next((item["content_sha256"] for item in contents if item.get("provenance") == "source" and item.get("is_active")), None)
                duplicate = db.execute("""SELECT m.id FROM memories m LEFT JOIN memory_contents c
                    ON c.memory_id = m.id AND c.provenance = 'source' AND c.is_active
                    WHERE m.account_id = %s AND m.kind = 'web_page' AND m.source_uri = %s
                    AND m.user_note = %s AND c.content_sha256 IS NOT DISTINCT FROM %s LIMIT 1""",
                    (account_id, uri, note, source_content)).fetchone()
            if duplicate:
                if project_name:
                    assign_project(db, account_id, duplicate["id"], project_name)
                return "duplicate", str(duplicate["id"])
            db.execute("""INSERT INTO memories (id, account_id, kind, title, source_uri, source_domain,
                captured_at, published_at, status, user_note, capture_reason, created_at, updated_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (memory_id, account_id, kind, title, uri, domain, timestamp(row.get("captured_at")),
                 timestamp(row["published_at"]) if row.get("published_at") else None,
                 row.get("status") if kind in {"web_page", "pdf"} and row.get("status") in {"ready", "partial"} else "partial" if kind == "image" else "pending" if kind == "pdf" else "ready",
                 note, row.get("capture_reason") if kind in {"web_page", "pdf"} else None,
                 timestamp(row.get("created_at")), timestamp(row.get("updated_at"))))
            for asset in assets:
                asset_id = uuid.uuid4()
                key = object_key(account_id, memory_id, asset_id)
                keys.append(key)
                body = originals[asset["id"]]
                target = path_for(key)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(body)
                db.execute("""INSERT INTO memory_assets (id, account_id, memory_id, role, object_key,
                    mime_type, byte_size, sha256, source_filename, created_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (asset_id, account_id, memory_id, asset["role"], key, asset["mime_type"],
                     asset["byte_size"], asset["sha256"], asset.get("source_filename"),
                     timestamp(asset.get("created_at"))))
            content_ids = {}
            for content in contents:
                body = content["body"]
                if hashlib.sha256(body.encode("utf-8")).hexdigest() != content["content_sha256"]:
                    raise ValueError("Content checksum mismatch")
                content_id = uuid.uuid4()
                content_ids[content["id"]] = content_id
                db.execute("""INSERT INTO memory_contents (id, account_id, memory_id, version, provenance,
                    body, content_sha256, processor_version, status, is_active, created_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (content_id, account_id, memory_id, content["version"], content["provenance"],
                     body, content["content_sha256"], content.get("processor_version"),
                     content["status"], content["is_active"], timestamp(content.get("created_at"))))
            for passage in passages:
                if passage["content_id"] not in content_ids:
                    raise ValueError("Passage refers to missing content")
                db.execute("""INSERT INTO content_passages (id, account_id, memory_id, content_id,
                    ordinal, body, page_number, section_label, start_offset, end_offset)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                    (uuid.uuid4(), account_id, memory_id, content_ids[passage["content_id"]],
                     passage["ordinal"], passage["body"], passage.get("page_number"),
                     passage.get("section_label"), passage.get("start_offset"), passage.get("end_offset")))
            if kind == "pdf" and not any(c.get("provenance") == "extracted" and c.get("is_active") for c in contents):
                db.execute("""INSERT INTO extraction_jobs (id, account_id, memory_id, job_type)
                    VALUES (%s, %s, %s, 'extract_pdf')""", (uuid.uuid4(), account_id, memory_id))
            if project_name:
                assign_project(db, account_id, memory_id, project_name)
    except BaseException:
        for key in keys:
            delete(key)
        raise
    return "imported", str(memory_id)


@router.post("/import")
async def import_data(request: Request, format: str = Query(pattern="^(contextos|bookmarks)$"),
                      session: dict = Depends(write_session)):
    chunks = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > MAX_IMPORT_BYTES:
            raise HTTPException(413, detail="Import exceeds 60 MiB")
        chunks.append(chunk)
    raw = b"".join(chunks)
    if not raw:
        raise HTTPException(422, detail="Import is empty")
    if format == "contextos":
        memories, contents, passages, assets, originals, project_for_memory = parse_export(raw)
    else:
        try:
            parser = BookmarkParser()
            parser.feed(raw.decode("utf-8-sig"))
        except UnicodeError as exc:
            raise HTTPException(422, detail="Bookmarks must use UTF-8") from exc
        if len(parser.items) > MAX_RECORDS:
            raise HTTPException(413, detail="Too many bookmarks")
        memories = []
        for item in parser.items:
            try:
                captured = datetime.fromtimestamp(int(item["add_date"]), timezone.utc).isoformat()
            except (ValueError, TypeError, OverflowError, OSError):
                captured = None
            memories.append({"id": str(uuid.uuid4()), "kind": "link", "title": item["title"].strip() or item["source_uri"],
                             "source_uri": item["source_uri"], "captured_at": captured})
        contents, passages, assets, originals, project_for_memory = [], [], [], {}, {}
    content_by_memory = {}
    passage_by_memory = {}
    asset_by_memory = {}
    for row in contents:
        content_by_memory.setdefault(row.get("memory_id"), []).append(row)
    for row in passages:
        passage_by_memory.setdefault(row.get("memory_id"), []).append(row)
    for row in assets:
        asset_by_memory.setdefault(row.get("memory_id"), []).append(row)
    memory_ids = {row.get("id") for row in memories}
    if format == "contextos" and (set(content_by_memory) | set(passage_by_memory) | set(asset_by_memory)) - memory_ids:
        raise HTTPException(422, detail="Export has unowned content or assets")
    if set(project_for_memory) - memory_ids:
        raise HTTPException(422, detail="Export has unowned project assignments")
    report = {"imported": 0, "duplicates": 0, "failed": 0, "items": []}
    for index, row in enumerate(memories):
        try:
            state, target_id = import_record(session["account_id"], row,
                content_by_memory.get(row["id"], []), passage_by_memory.get(row["id"], []),
                asset_by_memory.get(row["id"], []), originals,
                project_for_memory.get(row["id"], [None])[0])
        except (ValueError, KeyError, TypeError, HTTPException, UnicodeError) as exc:
            state, target_id = "failed", None
            error = exc.detail if isinstance(exc, HTTPException) else str(exc)
        report[{"imported": "imported", "duplicate": "duplicates", "failed": "failed"}[state]] += 1
        report["items"].append({"index": index, "source_id": row.get("id"), "status": state,
                                "memory_id": target_id, **({"reason": error[:200]} if state == "failed" else {})})
    return {"data": report, "error": None}
