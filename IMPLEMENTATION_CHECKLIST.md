# Context OS implementation checklist

Track the complete web product through Intelligent Memory, including the browser extension. See [ROADMAP.md](ROADMAP.md) for scope and product direction.

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
- [ ] Scaffold the web app, API, database migrations, background jobs, and shared validation/types as chosen in Phase 0.
- [ ] Implement account creation, sign-in, sign-out, session handling, and account recovery.
- [ ] Enforce user ownership checks on every memory, file, project, search, and assistant endpoint.
- [ ] Create persistent memory records with source type, title, URL or file reference, dates, user note, and processing status.
- [ ] Store original uploads separately from extracted text and AI-derived content.
- [x] Implement create, view, edit, and delete operations for the current note/link memory records.
- [ ] Build the Library screen with usable rows/cards, sorting, pagination, and source/status indicators.
- [ ] Build the Memory detail screen with original source access, metadata, notes, and processing feedback.
- [ ] Add file validation, size limits, safe file handling, and clear unsupported-input messages.
- [ ] Implement data export in the documented format, including source metadata and user-authored content.
- [ ] Implement permanent deletion across records, stored files, extracted text, and search data.
- [ ] Add meaningful tests for ownership boundaries, persistence, export, and deletion.
- [ ] **Phase 1 exit:** one user can create, reopen, edit, export, and delete a memory; another user cannot access it.

## Phase 2 — One-click browser capture

- [ ] Create a Manifest V3 Chrome/Chromium extension with the minimum permissions needed for explicit tab capture.
- [ ] Connect the extension to the signed-in web account and handle expired sessions.
- [ ] Save the current tab with one click: URL, title, capture time, and readable page text where accessible.
- [ ] Show immediate success, in-progress, duplicate, and failure feedback after the click.
- [ ] Allow adding or editing a note and project from the extension confirmation panel.
- [ ] Provide an optional action to save a screenshot of the visible tab area.
- [ ] Exclude password fields, form values, hidden content, and other unnecessary page data from routine text capture.
- [ ] Define and implement duplicate behavior for repeated saves of the same URL.
- [ ] Preserve a usable URL record when extraction fails; show the reason and retry path where possible.
- [ ] Link from the extension confirmation panel to the saved memory in the web app.
- [ ] Verify capture on ordinary articles, dynamic pages, restricted pages, and signed-in pages with clear outcomes.
- [ ] **Phase 2 exit:** a supported browser tab is saved with one click and can be found in the Library.

## Phase 3 — Cross-source capture and extraction

- [ ] Add manual URL capture in the web app with metadata and readable-text extraction where possible.
- [ ] Add standalone notes and pasted text/snippet capture.
- [ ] Add PDF upload, text extraction, page references, and scanned-PDF status handling.
- [ ] Add the selected launch document formats with extraction and clear unsupported-format feedback.
- [ ] Add image and screenshot upload with preview and source metadata.
- [ ] Add OCR for supported images and scanned PDFs, with processing limits and failure states.
- [ ] Build a capture queue/status model so slow extraction does not block saving or viewing an item.
- [ ] Allow reprocessing a source without overwriting the original or user-authored notes.
- [ ] Preserve extraction provenance and content version/hash so derived data can be refreshed safely.
- [ ] Verify one successful and one failed extraction path for each supported source type.
- [ ] **Phase 3 exit:** each supported source can be saved, inspected, deleted, and searched when text is available.

## Phase 4 — Search and organization

- [x] Index the current title, URL, and user note fields with SQLite FTS5 and verify search and reindexing after edits.
- [ ] Index titles, extracted text, user notes, and relevant source metadata for keyword/full-text search.
- [ ] Build the global Search screen with ranked results and clear reasons each result matched.
- [ ] Add filters for type, source/domain, capture date, project, tag, and collection where applicable.
- [ ] Add search within a project and preserve filters across result/detail navigation.
- [ ] Create projects and associate one memory with multiple projects without copying it.
- [ ] Add tags and collections with create, rename, assign, remove, and delete flows.
- [ ] Support moving from a search result to the original source or relevant text/page when available.
- [ ] Handle no results, ambiguous queries, extraction gaps, and deleted items clearly.
- [ ] Run the retrieval corpus from Phase 0; record correct-result rank and time to find the intended item.
- [ ] Test search isolation so one account's queries cannot return another account's content.
- [ ] **Phase 4 exit:** users can reliably recover known items across source types and organize them without duplication.

## Phase 5 — Context exploration

- [ ] Add manual relationships between memories with type, explanation, and provenance.
- [ ] Allow users to inspect, edit, and remove relationships.
- [ ] Build a simple graph view with readable labels, filtering, and direct links to memories.
- [ ] Provide a list alternative to the graph for accessibility and dense collections.
- [ ] Build a saved-item timeline with date, type, and project filters.
- [ ] Build project overview pages showing memories, project search, timeline, and connections.
- [ ] Add highlights/annotations with a stable page or text location where supported.
- [ ] Verify that deleting a memory cleans up links, graph entries, timeline entries, and annotations.
- [ ] **Phase 5 exit:** users can trace and manage context around a memory from project, graph, and timeline views.

## Phase 6 — Intelligent Memory

- [ ] Implement embeddings for new or changed content with a documented provider, usage limit, and retry behavior.
- [ ] Add hybrid keyword and semantic retrieval with source/date/project filters preserved.
- [ ] Evaluate vague-memory queries against the Phase 0 corpus and compare results with the keyword baseline.
- [ ] Show why semantic results matched and provide alternative results when confidence is low.
- [ ] Add related-memory suggestions with evidence and user approval/dismissal.
- [ ] Add suggested relationships/entities with visible provenance, review, and reversal controls.
- [ ] Add project-specific assistant questions over the user's saved sources.
- [ ] Add single-source summaries and multi-source comparisons on demand.
- [ ] Link assistant claims to the underlying memory and passage/page when available.
- [ ] Distinguish source facts, model inference, and missing evidence in assistant responses.
- [ ] Cache safe repeated operations and avoid regenerating unchanged content unnecessarily.
- [ ] Let users disable AI; core capture, library, projects, graph, timeline, and keyword search remain functional.
- [ ] Show AI processing disclosure and usage/cost limits before private content is sent to a provider.
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
- [ ] Test performance with a representative library size and document practical limits.
- [ ] Run end-to-end tests for capture, extraction, search, project use, deletion/export, and assistant citations.
- [ ] Test the extension on supported browser versions and prepare store listing, permissions description, and privacy disclosures.
- [ ] Prepare production hosting, domain, TLS, database/storage migrations, and deployment/rollback procedure.
- [ ] Write user help for saving, finding, exporting, deleting, and AI settings.
- [ ] Update developer setup, run, test, and deployment documentation.
- [ ] Complete a staging walkthrough of the entire user journey and resolve launch-blocking defects.
- [ ] **Phase 7 exit:** the deployed staging product meets functional, visual, accessibility, security, and recovery checks; public launch is ready.

## Release record

- Public launch date: _not set_
- Launch version: _not set_
- Known limitations at launch: _not set_
