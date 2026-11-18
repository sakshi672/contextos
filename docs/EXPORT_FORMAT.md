# Context OS account export, version 2

`GET /v1/export` downloads a private ZIP for the signed-in account. Keep the ZIP private: it contains source files, note text, and source URLs. The ZIP is an interchange copy, not a database backup. Version 2 includes all saved memory types, original files, project/collection/tag definitions, and their many-to-many memory assignments. Relationships, annotations, embeddings, and AI artifacts need a later format version.

| Entry | Content |
| --- | --- |
| `manifest.json` | `format: "contextos-account-export"`, `version: 2`, UTC `created_at`, and record counts. |
| `memories.jsonl` | One JSON object per memory: source type, title, URL/domain, captured and published dates, processing status, user note, capture method (`manual` or `browser`), available source author and image URL, and record dates. Older version 1 rows may omit the newer metadata. |
| `contents.jsonl` | Extracted or other versioned content with memory ID, provenance, body, SHA-256, processor version, status, active flag, and creation date. |
| `passages.jsonl` | Page-aware extracted passages with content ID, ordinal, page number, and offsets. Optional in older version 1 ZIPs. |
| `assets.jsonl` | Original-file metadata: memory ID, role, MIME type, byte count, SHA-256, source filename, creation date, and ZIP path. Internal storage keys are excluded. |
| `originals/<asset-id>` | Exact original bytes for each asset, checked against the asset SHA-256 during export and import. |
| `projects.jsonl` | Basic project IDs, names, and creation dates. Optional in older version 1 ZIPs. |
| `memory_projects.jsonl` | Memory-to-project IDs; multiple projects per memory are supported. |
| `collections.jsonl`, `tags.jsonl` | Collection and tag IDs, names, and creation dates, including empty groups. |
| `collection_memories.jsonl`, `memory_tags.jsonl` | Many-to-many collection and tag assignments. |

Every JSONL row has an `id`. Related rows refer to `memory_id` in `memories.jsonl`. Dates use ISO 8601 with a timezone. Empty JSONL files are valid. There are no paths from the local storage layout in the archive.

To restore, use **Import data** in the web app or send the ZIP bytes to `POST /v1/import?format=contextos` with the session cookie and `X-CSRF-Token`. The importer accepts versions 1 and 2. Import assigns new internal IDs, preserves supported metadata and original bytes, and reports each memory as imported, duplicate, or failed. A link with the same URL, a note with the same title and body, or a document with the same original checksum is a duplicate *within the receiving account*. Imported organization assignments are added to duplicates rather than replacing existing assignments. A malformed archive, unsafe path, count mismatch, or bad original checksum rejects the whole upload before any records are created. Individual unsupported or invalid memory records appear as failures in the report.

The importer accepts up to 60 MiB compressed, 100 MiB of declared expanded ZIP data, 5,000 memories, 10 MiB per TXT/Markdown original, 25 MiB per DOCX, 20 MiB per image or screenshot, and 50 MiB per PDF. The web importer also accepts UTF-8 Netscape bookmark HTML with `format=bookmarks`; it imports link URL, title, and the bookmark timestamp when present. Bookmark folders are not represented.
