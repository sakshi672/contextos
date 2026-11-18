# Context OS account export, version 1

`GET /v1/export` downloads a private ZIP for the signed-in account. Keep the ZIP private: it contains source files, note text, and source URLs. The ZIP is an interchange copy, not a database backup. The current version covers notes, pasted-text snippets, links, UTF-8 TXT/Markdown and DOCX documents, PDFs, PNG/JPEG/WebP images, browser captures, screenshots, and initial project assignments. Future project metadata, relationships, annotations, embeddings, and AI artifacts need a later format version.

| Entry | Content |
| --- | --- |
| `manifest.json` | `format: "contextos-account-export"`, `version: 1`, UTC `created_at`, and memory/content/asset counts. |
| `memories.jsonl` | One JSON object per memory: source type, title, URL/domain, captured and published dates, processing status, user note, and record dates. |
| `contents.jsonl` | Extracted or other versioned content with memory ID, provenance, body, SHA-256, processor version, status, active flag, and creation date. |
| `passages.jsonl` | Page-aware extracted passages with content ID, ordinal, page number, and offsets. Optional in older version 1 ZIPs. |
| `assets.jsonl` | Original-file metadata: memory ID, role, MIME type, byte count, SHA-256, source filename, creation date, and ZIP path. Internal storage keys are excluded. |
| `originals/<asset-id>` | Exact original bytes for each asset, checked against the asset SHA-256 during export and import. |
| `projects.jsonl` | Basic project IDs, names, and creation dates. Optional in older version 1 ZIPs. |
| `memory_projects.jsonl` | Memory-to-project IDs. Optional in older version 1 ZIPs. One project per memory is supported in the current importer. |

Every JSONL row has an `id`. Related rows refer to `memory_id` in `memories.jsonl`. Dates use ISO 8601 with a timezone. Empty JSONL files are valid. There are no paths from the local storage layout in the archive.

To restore, use **Import data** in the web app or send the ZIP bytes to `POST /v1/import?format=contextos` with the session cookie and `X-CSRF-Token`. Import assigns new internal IDs, preserves supported metadata and original bytes, and reports each record as imported, duplicate, or failed. A link with the same URL, a note with the same title and body, or a document with the same original checksum is a duplicate *within the receiving account*. A malformed archive, unsafe path, count mismatch, or bad original checksum rejects the whole upload before any records are created. Individual unsupported or invalid records appear as failures in the report.

The importer accepts up to 60 MiB compressed, 100 MiB of declared expanded ZIP data, 5,000 memories, 10 MiB per TXT/Markdown original, 25 MiB per DOCX, 20 MiB per image or screenshot, and 50 MiB per PDF. The current web importer also accepts UTF-8 Netscape bookmark HTML with `format=bookmarks`; it imports link URL, title, and the bookmark timestamp when present. Bookmark folders are not represented in version 1.
