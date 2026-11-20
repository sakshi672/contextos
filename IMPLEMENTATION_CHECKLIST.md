# Context OS implementation checklist

Track Release 1 of the web product through Intelligent Memory, including the browser extension. Its competitive goal is to recover vaguely remembered information with source provenance and project context; feature inclusion does not itself establish competitive superiority. Release 2 covers larger platform expansions, not routine features that fit the existing architecture. See [ROADMAP.md](ROADMAP.md) for scope and product direction.

Mark a box `[x]` only when the task is implemented and its stated behavior has been verified. Keep unfinished work as `[ ]`. Add a short link or note beside a completed item when the evidence is not obvious from the code. Complete each phase's exit check before treating the phase as done. These are internal build phases; public launch comes after Phase 7.

## Phase 0 — Decisions, architecture, and visual design

- [x] Set up the first local stack: React/TypeScript/Vite frontend, Python API, and SQLite FTS5; document how to run it. See [README.md](README.md) and [architecture notes](docs/ARCHITECTURE.md).
- [x] Confirm launch scope and supported browsers: Chrome/Chromium extension plus responsive web app. See [Phase 0 specification](docs/PHASE_0_SPEC.md).
- [x] Choose and document the frontend, backend, database, job processing, and file storage stack. See [Phase 0 specification](docs/PHASE_0_SPEC.md).
- [x] Define the hosted account model, user data boundaries, deployment environment, and backup approach. Provider and region are chosen before staging. See [Phase 0 specification](docs/PHASE_0_SPEC.md).
- [x] Define launch file formats, upload limits, URL capture limits, and extraction failure behavior. See [Phase 0 specification](docs/PHASE_0_SPEC.md).
- [x] Define the memory schema, source provenance fields, content versions, and derived-data lifecycle. See [Phase 0 specification](docs/PHASE_0_SPEC.md).
- [x] Define the extension-to-app authentication and capture API contract. See [Phase 0 specification](docs/PHASE_0_SPEC.md).
- [x] Define the AI provider boundary, user consent flow, default AI state, cost limits, and fallback behavior. See [Phase 0 specification](docs/PHASE_0_SPEC.md).
- [x] Define export format and deletion semantics for files, indexes, embeddings, and generated content. See [Phase 0 specification](docs/PHASE_0_SPEC.md).
- [x] Create a small representative corpus and retrieval queries for later search evaluation. See [seed cases](evaluation/seed_cases.json).
- [x] Design an original Context OS identity: logo/wordmark direction, light-theme palette, type scale, spacing, radii, borders, shadows, icons, and motion rules. See [brand direction](design/BRAND.md).
- [x] Create high-fidelity light-theme prototypes for Search, Library, Memory detail, and extension save feedback. See [interactive prototype](design/prototype.html).
- [x] Review populated, empty, loading, error, hover, focus, and small-screen states in those prototypes. See [visual review notes](design/REVIEW.md); true 390 px device QA remains for implementation.
- [x] Document the approved working design system and interaction patterns for implementation. Light theme selected as the current default; see [brand system](design/BRAND.md) and [review](design/REVIEW.md).
- [x] **Phase 0 exit:** architecture and light-theme design decisions are recorded; the local API workflow tests and frontend build pass using the documented commands. See [Phase 0 specification](docs/PHASE_0_SPEC.md), [visual system](design/BRAND.md), and [README](README.md).

## Phase 1 — Core memory platform

- [x] Build the first persistent local note/link record flow and Library/detail UI; verify create, reopen, edit, and delete over HTTP.
- [x] Scaffold React/TypeScript, the typed API client, FastAPI/Pydantic request validation, PostgreSQL migrations, and durable background jobs as chosen in Phase 0. See [backend foundation](backend/README.md), [Docker Compose](compose.yaml), and the live API tests. New source types will add their contracts and handlers in their respective phases.
- [x] Start the versioned FastAPI service with liveness and database-readiness endpoints. HTTP smoke check: liveness returned 200; readiness returned 503 without PostgreSQL configured. See [API entry point](backend/contextos/main.py).
- [x] Add a read-only snapshot of the SQLite prototype before the PostgreSQL cutover. Verified record count, checksum, Unicode preservation, source unchanged, and refusal to overwrite in [snapshot test](tests/test_legacy_export.py).
- [x] Implement the first PostgreSQL account-scoped note/link API slice with cookie sessions and CSRF checks. Live [integration test](tests/test_postgres_api.py) verifies two-account isolation, create/edit/delete, login, logout, and session refresh.
- [x] Switch the local web app's note/link and account flows to PostgreSQL. The legacy SQLite source contained zero memories; a read-only ZIP snapshot is retained locally. The [frontend build](README.md), live API tests, and Vite-to-FastAPI readiness proxy check pass.
- [x] Add the first private file workflow for UTF-8 TXT/Markdown: 10 MiB upload limit, original stored under a generated key, durable extraction job, extracted content in PostgreSQL, owner-only download/read, and deletion of the local original. Live [tests](tests/test_postgres_api.py) cover success, invalid encoding, ownership, expired worker leases, and object-deletion retry. Other launch formats remain open.
- [x] Add a first account-scoped ZIP export for current note/link/document records, extracted text, and original files. The [live test](tests/test_postgres_api.py) verifies source bytes and metadata are present, a second account's records are absent, and version 1 can be imported into another account. Future organization data remains open.
- [x] Add Library count, title/updated/recent sorting, file-type filtering, and page navigation. The [live API test](tests/test_postgres_api.py) verifies paginated totals and ordering without cross-account records.
- [x] Implement account creation, sign-in, sign-out, session handling, and one-time password recovery with session revocation. Local development uses an ignored recovery inbox; hosted SMTP is configurable. Registration verification and abuse controls remain release work.
- [x] Enforce account ownership on every current memory, file, export, and import endpoint, including cross-account read/write tests. Project, search, and assistant endpoints will receive the same checks when implemented.
- [x] Create persistent records for current note/link/text-document types with title, URL or original-file reference, dates, user note, and processing status.
- [x] Store current original uploads separately from extracted text with explicit provenance. Future AI-derived content will use its separate provenance in later phases.
- [x] Implement create, view, edit, and delete operations for the current note/link memory records.
- [x] Build the Library screen with usable rows/cards, sorting, pagination, and source/status indicators for current note, link, and text-document types. See [web app](src/App.tsx) and [API test](tests/test_postgres_api.py).
- [x] Build the Memory detail screen with original source access, metadata, notes, and processing feedback for current types. See [web app](src/App.tsx) and [private-file test](tests/test_postgres_api.py).
- [x] Validate current TXT/Markdown uploads for extension, 10 MiB size, UTF-8, and binary NULs before storage; reject unsupported inputs clearly. ZIP and bookmark imports enforce format and size limits. Additional source types need their own validation in Phase 3.
- [x] Implement account export with source metadata, originals, extracted text, and user notes in the [documented version 1 format](docs/EXPORT_FORMAT.md).
- [x] Import UTF-8 Netscape browser bookmark HTML and the version 1 Context OS ZIP for current note/link/document types, preserving supported metadata and reporting duplicates and failures. Live round-trip and bookmark tests in [tests/test_postgres_api.py](tests/test_postgres_api.py). Additional bookmark encodings and future source types remain for later phases.
- [x] Implement permanent deletion for current records, extracted text, search fields, and originals. Object cleanup is transactionally queued and retried after unlink failures; see [migration](backend/migrations/0002_object_deletions.sql) and [live test](tests/test_postgres_api.py). Future embeddings and graph data will need deletion coverage in their phases.
- [x] Add live PostgreSQL tests for account ownership, persistence, export/import round trips, recovery, malformed inputs, and deletion retries in an isolated test schema.
- [x] **Phase 1 exit (local core platform):** a user can create, reopen, edit, export/import, and delete current memories; another account cannot access them. The [live PostgreSQL suite](tests/test_postgres_api.py) verifies these flows. Hosted launch controls remain in Phase 7.

## Phase 2 — One-click browser capture

- [x] Create a Manifest V3 Chrome/Chromium extension using `activeTab`, `scripting`, and `storage`, with local API host access and optional HTTPS API host access. See [extension setup](extension/README.md).
- [x] Pair with the signed-in web account using a ten-minute code and a revocable, 90-day capture-scoped credential. Expired/revoked credentials return to pairing. Live [API tests](tests/test_postgres_api.py) cover one-time code use and revocation.
- [x] Implement one-click current-tab save in the popup: URL, title, time, and up to 2 MiB of readable visible text when accessible. Browser verification is still pending below.
- [x] Implement in-progress, saved, duplicate, metadata-only, and error feedback in the popup.
- [x] Allow editing a note and assigning or creating one project from the extension confirmation panel. Basic project assignments are included in account export/import.
- [x] Add an optional visible-tab screenshot action with a private, owner-only file and 20 MiB server limit.
- [x] Implement a text collector that skips form controls and values, contenteditable, hidden/inert/aria-hidden elements, and script/style content. Manual browser verification remains open below.
- [x] Repeated saves of the same URL and unchanged readable text/note return the prior memory with `already_saved`; changed content or note creates a new event.
- [x] Preserve a metadata-only URL/title record with a reason when text access fails, and expose retry in the popup and Memory detail.
- [x] Link the confirmation panel to the exact saved memory in the web app.
- [ ] Verify the unpacked extension in Chrome/Chromium on ordinary articles, dynamic pages, restricted pages, signed-in pages, and repeated captures. Check that hidden/form text is absent, screenshot content matches the visible area, and the popup layout feels polished. See [manual matrix](extension/README.md).
- [ ] **Phase 2 exit:** a supported browser tab is saved with one click and can be found in the Library.

## Phase 3 — Cross-source capture and extraction

- [x] Add manual URL capture in the web app with public-network-only, bounded readable-text extraction and available source, author, publication date, and image metadata. Show whether extracted text or only a URL was saved; no full-page archive is retained.
- [x] Add standalone notes and pasted text/snippet capture. Pasted text is versioned user content that can be edited, searched, and exported/imported.
- [x] Add PDF upload (50 MiB, 200 pages), worker-based text extraction and OCR for up to 40 image-only pages, page references, and a partial status when some pages still lack text. Preserve the original when extraction fails.
- [x] Add the selected launch document formats (UTF-8 TXT/Markdown and DOCX) with extraction and clear unsupported-format feedback.
- [x] Add PNG/JPEG/WebP image and screenshot-file upload with a private preview and original filename, MIME type, and size metadata. Browser visible-tab screenshots remain a separate Phase 2 action.
- [x] Add OCR for supported images and scanned PDFs, with pixel, page, and text limits and partial/failed states.
- [x] Build a durable extraction-job queue and pending/processing/ready/partial/failed statuses so files and manually fetched URLs appear in Library before processing completes.
- [x] Allow reprocessing saved TXT/Markdown, DOCX, PDF, image, and manual URL sources without overwriting originals, prior extracted text, or user-authored notes.
- [x] Preserve extraction provenance and content version/hash so derived data can be refreshed safely.
- [x] Verify successful and failed extraction paths for TXT/Markdown, DOCX, images, PDFs, and manual URLs, including owner isolation and retained prior text on failed refresh.
- [x] **Phase 3 exit:** each supported source can be saved, inspected, deleted, and searched when text is available. API integration tests cover the source flows; real-browser QA remains tracked under Phase 2.

## Phase 4 — Search and organization

- [x] Index the current title, URL, and user note fields with SQLite FTS5 and verify search and reindexing after edits.
- [x] Index titles, extracted text, user notes, and relevant source metadata for keyword/full-text search.
- [x] Build the global Search screen with ranked results and clear reasons each result matched.
- [x] Add filters for type, source/domain, capture date, project, tag, and collection where applicable.
- [x] Add search within a project and preserve filters across result/detail navigation.
- [x] Create projects and associate one memory with multiple projects without copying it.
- [x] Add tags and collections with create, rename, assign, remove, and delete flows.
- [x] Support moving from a search result to the original source or relevant text/page when available.
- [x] Handle no results, ambiguous queries, extraction gaps, and deleted items clearly.
- [x] Run the retrieval corpus from Phase 0; record correct-result rank and automated query-to-identification time in [the baseline results](evaluation/keyword_baseline_results.json). Human UI task time remains a Phase 7 validation.
- [x] Test search isolation so one account's queries cannot return another account's content.
- [x] **Phase 4 exit:** users can recover known items across source types and organize them without duplication. The six synthetic retrieval cases reach the expected item within two results (five rank first); broader observed retrieval quality remains for Phase 6 and public-readiness testing.

## Phase 5 — Context exploration

- [x] Add manual relationships between memories with type, explanation, and provenance.
- [x] Allow users to inspect, edit, and remove relationships.
- [x] Build a simple graph view with readable labels, filtering, and direct links to memories.
- [x] Provide a list alternative to the graph for accessibility and dense collections.
- [x] Build a saved-item timeline with date, type, and project filters.
- [x] Build project overview pages showing memories, project search, timeline, and connections.
- [x] Add highlights/annotations with a stable page or text location where supported; changing source text flags the anchor as stale.
- [x] Verify that deleting a memory cleans up links, graph entries, timeline entries, and annotations (live PostgreSQL test).
- [x] **Phase 5 exit:** users can trace and manage context around a memory from project, graph, and timeline views. Migration applied, production build passed, and 32 tests passed; visual/accessibility review remains in Phase 7.

## Phase 6 — Intelligent Memory

- [ ] Implement embeddings for new or changed content with a documented provider, usage limit, and retry behavior.
- [ ] Add hybrid keyword and semantic retrieval with source/date/project filters preserved; combine available partial clues such as meaning, entities, approximate dates, source, and extracted image text. Do not imply unsupported visual matching.
- [ ] Evaluate vague-memory queries against the Phase 0 corpus and compare results with the keyword baseline.
- [ ] Show why semantic results matched and provide alternative results when confidence is low.
- [ ] Add related-memory suggestions with evidence and user approval/dismissal.
- [ ] Add suggested relationships/entities with visible provenance, review, and reversal controls.
- [ ] Suggest relevant memories for a project, including memories already associated with other projects; let the user approve or dismiss associations.
- [ ] Surface recurring themes across selected memories and suggest tags or collections for user review.
- [ ] Add project-specific assistant questions over the user's saved sources, including research synthesis and identification of unanswered questions where evidence permits.
- [ ] Add single-source summaries and multi-source comparisons on demand.
- [ ] Generate ideas grounded in selected memories, identifying supporting sources and model inference.
- [ ] Link assistant claims to the underlying memory and passage/page when available.
- [ ] Distinguish source facts, model inference, and missing evidence in assistant responses.
- [ ] Cache safe repeated operations and avoid regenerating unchanged content unnecessarily.
- [ ] Let users disable AI; core capture, library, projects, graph, timeline, and keyword search remain functional.
- [ ] Show AI processing disclosure and usage/cost limits before private content is sent to a provider; prohibit training on private memories without explicit user consent.
- [ ] Include embeddings and generated content in deletion/reprocessing behavior.
- [ ] Test citations against source passages and test the disabled/over-budget AI states.
- [ ] **Phase 6 exit:** vague retrieval and source-grounded assistance work across a project, with measured quality and optional AI.

## Phase 7 — Public release readiness

- [ ] Apply the approved visual system consistently across every web app and extension screen.
- [ ] Review visual polish at common desktop and small-screen sizes, including dense and empty data states.
- [ ] Verify keyboard navigation, focus order, contrast, reduced motion, screen-reader labels, and graph alternative.
- [ ] Complete security review for authentication, authorization, uploads, URL fetching, extension messaging, and AI data flow.
- [ ] Add rate limits, abuse protection, safe error handling, and monitoring without logging raw private content.
- [ ] Verify backups and a restore procedure with a test restore.
- [ ] Include relationships and annotations in account ZIP export/import and verify a round trip.
- [ ] Test performance with a representative library size and document practical limits.
- [ ] Run end-to-end tests for capture, extraction, search, project use, deletion/export, and assistant citations.
- [ ] Test the extension on supported browser versions and prepare store listing, permissions description, and privacy disclosures.
- [ ] Prepare production hosting, domain, TLS, database/storage migrations, and deployment/rollback procedure.
- [ ] Write user help for saving, finding, exporting, deleting, and AI settings.
- [ ] Update developer setup, run, test, and deployment documentation.
- [ ] Complete a staging walkthrough of the entire user journey and resolve launch-blocking defects.
- [ ] **Phase 7 exit:** the deployed staging product meets functional, visual, accessibility, security, and recovery checks; public launch is ready.

## Release 2 ? Platform expansion

- [ ] Add portable, permission-scoped access to selected memories and project knowledge through an API and MCP.
- [ ] Expand import from supported external services and additional formats.
- [ ] Explore desktop and mobile capture, selected activity history, and optional encrypted cross-device sync.
- [ ] Explore context-aware resurfacing and optional shared project spaces.

These are future scope, not prerequisites for Release 1. Implement smaller compatible improvements in Release 1 when practical.

## Release record

- Public launch date: _not set_
- Launch version: _not set_
- Known limitations at launch: _not set_
