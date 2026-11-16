# Phase 0 product and architecture specification

Status: **implementation baseline for the complete web product**. The visual prototype is in [`design/prototype.html`](../design/prototype.html). Hosting provider, data region, and the first paid AI provider remain deployment choices; their interfaces and constraints are defined here. The product stays private during development and is made public only after Phase 7.

## Launch boundary and platforms

The first public product includes the responsive web app and a Manifest V3 extension for current Chrome/Chromium browsers. The web app supports the library, search, projects, collections, tags, manual relationships, graph, timeline, data controls, and optional Intelligent Memory features. The extension offers explicit, one-click capture of the current browser tab. Desktop applications, continuous screen history, mobile apps, email ingestion, collaboration, public API, and MCP are outside this release.

The extension uses `activeTab` and `scripting` for a user-invoked page read. It requests narrow host access for the Context OS API, not blanket access to all visited sites. A separate optional action captures the *visible tab area*. It does not claim to save the whole screen or a complete scrollable page. Restricted browser pages can return a clear URL-only or unsupported result. This follows Chrome's [activeTab](https://developer.chrome.com/docs/extensions/develop/concepts/activeTab), [scripting](https://developer.chrome.com/docs/extensions/reference/api/scripting/), and [tabs](https://developer.chrome.com/docs/extensions/reference/api/tabs/) API contracts.

## Technology and deployment

| Concern | Chosen direction |
| --- | --- |
| Web interface | React + TypeScript + Vite; one shared design system and typed API client. |
| Browser capture | Chrome/Chromium Manifest V3 extension in TypeScript; package separately from the web app. |
| Public API | FastAPI on Python, with versioned REST endpoints and generated OpenAPI schema. Replace the current standard-library development server during Phase 1. |
| Database | PostgreSQL for accounts, memories, projects, relationships, jobs, and keyword search. Use migrations from the first production schema. |
| Search | PostgreSQL full-text indexes for the baseline. Add pgvector embeddings and hybrid ranking in Phase 6 after evaluating the keyword baseline. |
| Original files | S3-compatible private object storage in production; filesystem adapter for local development. No public object URLs. |
| Background work | Separate Python worker polling durable jobs in PostgreSQL with claim/lease, retry, and failure states. One worker is sufficient initially. |
| Deployment | Static web build behind HTTPS; containerized API and worker; managed PostgreSQL and private object storage. Pick a provider and region before staging. |
| Configuration | Environment variables and a secret store for production credentials; `.env.example` contains names only. |

PostgreSQL provides built-in [full-text search](https://www.postgresql.org/docs/current/textsearch.html). [pgvector](https://github.com/pgvector/pgvector) can store vectors with relational data when semantic search is added. A durable worker is preferable for file extraction and OCR because these can outlive a request; FastAPI's own [background task guidance](https://fastapi.tiangolo.com/tutorial/background-tasks/) calls out heavier work as a case for a separate worker. These are architecture choices, not claims about current implementation.

The current Python standard-library API and SQLite database are local prototype code. Data migration from `data/context.db` to the production schema will be implemented and tested before accounts are introduced; the existing data file must never be silently discarded.

## Account and data boundary

- One individual account owns each memory, file, search index entry, project, collection, relationship, annotation, embedding, and generated artifact. Every read and write query includes the authenticated account identifier.
- Web sessions use secure, HTTP-only, SameSite cookies with CSRF protection on writes. Passwords use a memory-hard password hash; registration, sign-in, sign-out, verified email recovery, and session revocation are required before hosted access.
- Initial launch is single-person accounts. Shared spaces and team roles are deferred.
- The extension uses a revocable, capture-scoped credential obtained by a short-lived pairing code displayed in the signed-in web app. The extension stores the credential in extension storage, never in page JavaScript or a query string. Pairing codes expire after 10 minutes and can be used once. Server storage keeps only a token hash. Disconnecting the extension revokes the credential.
- A staging instance uses non-production accounts and storage. The production provider, data region, retention period, and recovery targets are recorded before staging. Daily database backups and object-storage version/recovery capability are required; a restore is tested in Phase 7.

## Launch inputs and limits

| Input | Launch handling | Initial limit |
| --- | --- | --- |
| Current browser tab | URL, title, capture time, readable visible page text, user note, optional visible screenshot. | 2 MiB normalized text; screenshot 20 MiB. |
| Manual URL | URL and metadata; safe server-side fetch of public HTTP(S) pages, with redirect and private-network blocking. | 2 MiB extracted text; 10-second fetch budget. |
| PDF | Original upload, page-aware text extraction; OCR for image-only pages where supported. | 50 MiB, 200 pages. |
| DOCX | Original upload and text extraction. | 25 MiB. |
| TXT / Markdown | Original upload and decoded plain text. | 10 MiB. |
| PNG / JPEG / WebP | Original upload, preview, and OCR. | 20 MiB. |
| Note / snippet | User-entered text. | 20,000 characters. |

Limits are enforced on both client and server and can be lowered by deployment configuration. Unsupported formats are rejected before storage with a clear message. A capture becomes a usable memory as soon as its source metadata is stored. Extraction then reports `pending`, `processing`, `ready`, `partial`, or `failed`. A failed extraction never removes the original source, URL, or user note. The user can retry safe extraction. No automatic full-page archive is promised. Routine DOM capture excludes form controls, passwords, hidden elements, and script/style content; users may inspect and delete the result.

## Canonical memory model

All primary keys are UUIDs. Tables use `account_id`, UTC creation/update timestamps, and foreign-key deletion rules. The following is the production model to implement with migrations:

| Table | Essential fields and purpose |
| --- | --- |
| `accounts`, `sessions`, `extension_credentials` | Account identity, web session/recovery data, hashed and revocable extension tokens. |
| `memories` | `id`, `account_id`, `kind`, `title`, `source_uri`, `source_domain`, `captured_at`, `published_at`, `status`, `user_note`, `created_at`, `updated_at`. |
| `memory_assets` | Original file or screenshot object key, MIME type, byte size, hash, source filename, and storage state. |
| `memory_contents` | Source/extracted text versions, content hash, parser version, extraction status, and provenance (`source`, `user`, `extracted`, `generated`). User-authored text is never replaced by a worker. |
| `content_passages` | Ordered text chunks with page/section offsets for search results and citations. |
| `projects`, `project_memories` | Project metadata and many-to-many links to memories. |
| `collections`, `collection_memories`, `tags`, `memory_tags` | User organization without duplicating source content. |
| `relationships`, `annotations` | User or model origin, evidence/location, review state, and reversible links. |
| `extraction_jobs` | Durable processing state, attempt count, lease, error code, and next retry time. |
| `embeddings`, `generated_artifacts` | Model/version, source content hash, created time, and usage for derived AI data. |
| `audit_events` | Metadata-only account/security events; never raw source text or secrets. |

The original source and user-authored data are authoritative. Derived text, search documents, OCR, embeddings, suggestions, and summaries are versioned by source hash and processor/model version. Reprocessing creates a new derived version, changes the active pointer only after success, and leaves user notes intact. Deletion removes all versions. Search indexes are rebuildable from retained source and extracted text. Relationship origin and suggestion review remain visible.

## Capture and search contracts

API responses use `{ data, error }` with stable error codes. The authenticated web API and scoped extension API share memory identifiers. Write operations accept an `Idempotency-Key` to make retries safe.

| Endpoint | Purpose |
| --- | --- |
| `POST /v1/memories` | Save note or manual URL. Returns record and processing status. |
| `GET /v1/memories`, `GET /v1/memories/{id}` | List/search and inspect an owned memory. |
| `PATCH /v1/memories/{id}`, `DELETE /v1/memories/{id}` | Edit user fields or permanently delete the memory and derived data. |
| `POST /v1/uploads`, `POST /v1/uploads/{id}/complete` | Start and finalize private file upload with type/size verification. |
| `POST /v1/extension/pairings` | Signed-in web session creates a one-time pairing code. |
| `POST /v1/extension/tokens` | Exchange the code for a capture-scoped credential. |
| `POST /v1/captures` | Extension sends current tab snapshot. Returns a saved memory immediately; extraction may continue. |
| `GET /v1/search` | Keyword search with type, source, date, and project filters. |
| `GET /v1/exports/{id}` | Download a completed account export. |

`POST /v1/captures` accepts `source_url`, `title`, `captured_at`, `readable_text`, `user_note`, optional `project_id`, and optional screenshot upload reference. The server records whether each field came from the browser, the user, or extraction. The client never sends full page HTML or form values. If extraction is restricted, it sends URL/title with a reason code; the app does not imply that the page text was archived. Capture is rejected for unsupported schemes and blocked domains. Repeated capture of one URL creates a new event only if content or the user's note changed; otherwise it returns the prior memory with `already_saved: true`.

## AI and cost boundary

AI is **off by default**. Capture, files, keyword search, projects, timeline, and manual relationships work without it. The user sees the provider, data sent, and estimated usage before enabling cloud AI. A provider adapter separates embedding, summarization, and question-answering calls from the core API. The first provider is selected before Phase 6; no provider key is needed for earlier phases.

Each account has a configurable monthly spending ceiling, defaulting to zero until the user opts in. The server enforces a hard ceiling before model calls and shows usage in settings. Embeddings run only for new/changed source hashes; summaries and answers run on demand and may be cached when source hashes match. Over-budget and provider-failure states fall back to keyword search. Generated claims require passage/page citations where possible, and inference or missing evidence is labeled. Disabling AI stops new calls and offers deletion of derived AI data.

## Export and deletion

An account export is a ZIP containing a versioned `manifest.json`, JSONL records for memories/projects/relationships/annotations, and original uploaded files under stable IDs. The manifest records source URLs, capture dates, provenance, and extraction status; generated summaries are labeled separately. The format is documented and can be imported later.

Deleting a memory removes database records, originals and screenshots, extracted versions, passages, full-text entries, embeddings, generated artifacts, annotations, and relationship edges. A background cleanup job retries object deletion; the user sees `deletion_pending` until cleanup succeeds. Deleting an account uses the same pipeline across all owned records. Backups follow the documented retention window, and user-facing copy states the delay before backup expiry. Export and deletion are tested on mixed source types before release.

## Retrieval evaluation seed

The first corpus is in [`evaluation/seed_cases.json`](../evaluation/seed_cases.json). It contains synthetic items and exact, partial, source/date, and meaning-based queries with intended results. It is a development seed, not evidence of product quality; real user queries are added later. Measure rank of intended item, success in top 5, and time to open the source. Keyword search is the baseline for judging the later hybrid search.
