# Context OS

Context OS is a personal memory system for capturing, connecting, and finding information across sources and projects, including when the user remembers only partial clues. The intended first release is a web app and browser extension with source-preserving capture, project memory, an explainable knowledge graph, hybrid retrieval, and a source-grounded assistant. The current implementation is a **local development slice**: a light-theme library with account sign-in, private uploads, import/export, explicit browser capture, project exploration, and optional Intelligent Memory code. Cloud AI is off by default and has not been evaluated with a live API key. The complete product scope and sequence are in [ROADMAP.md](ROADMAP.md) and [IMPLEMENTATION_CHECKLIST.md](IMPLEMENTATION_CHECKLIST.md).

## Planned first release

Release 1 combines a responsive web app and Chrome/Chromium extension with:

- One-click browser capture, links, notes, PDFs, supported documents, and images; extracted text, OCR, and source information where available.
- A searchable library with keyword and semantic retrieval, filters, match explanations, and recovery from partial clues.
- Projects, tags, collections, annotations, a saved-memory timeline, and an explainable graph with user-controlled connections.
- Related-memory and project suggestions, plus an optional AI assistant that summarizes, compares, and answers with sources and clearly identified uncertainty.
- Import and export, deletion controls, and transparent, user-controlled AI processing.

The goal is a useful competitive experience across these features; no single feature guarantees an advantage. Desktop and mobile capture, selected activity history, public API/MCP access, and optional sync are later platform work. Product-market validation is not a prerequisite for implementing the planned first-release features.

Phase 0 decisions are in the [product and architecture specification](docs/PHASE_0_SPEC.md). The [interactive design prototype](design/prototype.html) shows Search, Library, Memory detail, and extension save feedback with sample data. Open it directly in a browser; it is a design study, separate from the running app. The [visual system](design/BRAND.md) uses a light theme as the working implementation baseline.

## Run locally

Requirements: Node.js 22+, npm, Python 3.13+, and Docker Desktop running Linux containers.

1. Install frontend dependencies: `npm.cmd install` on Windows or `npm install` elsewhere.
2. Create a virtual environment and install backend dependencies: `python -m venv .venv`, then `.venv\Scripts\python -m pip install -r backend\requirements.txt` on Windows.
3. Generate local settings once: `.venv\Scripts\python -m backend.contextos.local_db init`. If `backend/.env` already exists, keep it; do not reinitialize the password.
4. Start PostgreSQL and apply migrations: `docker compose --env-file backend/.env up -d postgres`, then `.venv\Scripts\python -m backend.contextos.local_db migrate`.
5. Start the API in one terminal: `.venv\Scripts\python -m backend.contextos.local_db serve`.
6. Start the extraction, file-cleanup, and optional embedding worker in another terminal: `.venv\Scripts\python -m backend.contextos.local_db worker`.
7. Start the web app in a third terminal: `npm.cmd run dev` on Windows or `npm run dev` elsewhere.
8. Open `http://127.0.0.1:5173/` and create a local account.

To use one-click browser capture, build the extension with `npm.cmd run build:extension` and follow [the extension setup](extension/README.md). Apply the latest database migrations and restart the API before pairing. Do not publish the web app or extension yet.

The FastAPI service listens only on `127.0.0.1:8766`; Vite forwards `/v1` calls to it. New account and memory data is stored in PostgreSQL with pgvector in a named Docker volume and persists across restarts. `data/context.db` and `data/legacy-snapshot.zip` are retained as local backups from the SQLite prototype; the source had zero memories at cutover. Do not expose the development API to the internet; recovery, rate limits, and release security checks remain on the checklist.

See the [FastAPI/PostgreSQL backend notes](backend/README.md) for API and database details. The older `server/` SQLite API is kept only for snapshot and regression reference; the running web app uses PostgreSQL.

## Verify

- Backend workflow tests: `python -m unittest discover -s tests -v`
- Frontend type check and production build: `npm.cmd run build` (or `npm run build`)

Current manual flow: register, save a link, note, webpage, snippet, image, PDF, or document. Open a memory to inspect its text, add a precise highlight, or connect it to another memory with an explanation. Use **Projects & organization** to create a project, then open its overview for memories, scoped search, timeline, and connections. The sidebar also offers a global timeline and graph/list connection views. Use **Export your data** to download an account-scoped ZIP and **Import data** to restore it or import browser bookmark HTML. Reload and sign back in to check PostgreSQL persistence. For local password recovery, use **Forgot password?** and open the newest link for your account in `data/recovery-outbox/`.

## Current limits

Phase 3 supports pasted-text snippets, manual webpage capture, image uploads, PDFs, and DOCX files. Use **Save webpage** to fetch readable text from a public HTTP(S) URL, including available title, author, publication date, and image link. The app shows when only the URL could be saved; it does not archive the full HTML page. **Save pasted text** stores up to 2 MiB of editable, searchable text with a separate note. **Upload image** accepts PNG, JPEG, or WebP originals up to 20 MiB and runs OCR. **Upload PDF** accepts files up to 50 MiB and 200 pages; a worker extracts selectable text and OCRs up to 40 image-only pages, with page references. **Upload DOCX** accepts files up to 25 MiB and extracts paragraph and table text. Files with no detected text show a partial status. Use **Reprocess original** or **Refresh page text** to retry processing while retaining saved originals, user notes, and previous extracted text. These source types are included in account export/import.

Phase 5 relationships and annotations are stored in PostgreSQL but are not yet included in account ZIP export/import. Complete round-trip coverage is tracked before public release.

Phase 6 adds optional Intelligent Memory. Without an API key, the settings screen shows AI as unavailable and all core features continue to work. A future local test can put `CONTEXT_OS_OPENAI_API_KEY=...` in the ignored `backend/.env`, then restart both API and worker. Enabling AI for an account requires an explicit cloud-processing checkbox and a monthly token ceiling. Enabled accounts get retryable embeddings, hybrid search, similarity suggestions requiring review, and cited project/memory answers. Model output is cached against source text and invalidated when that text changes. The local tests mock provider calls; live retrieval quality, cost, and model behavior remain unverified. See [Phase 6 notes](docs/PHASE_6_AI.md).

**Save a link** still stores only user-entered metadata; **Save webpage** fetches public page text. The extension can save visible page text after an explicit click, with metadata-only fallback when access is restricted. Uploads support TXT, Markdown, DOCX, PDF, PNG, JPEG, and WebP. Keyword search covers titles, notes, source details, and active extracted text, with account-scoped filters and an explicitly labeled partial-word fallback. The web app supports multiple projects, tags, and collections per memory, and ZIP exports preserve these assignments. Hosted email verification, abuse controls, browser compatibility checks, live AI evaluation, and release security checks are outstanding. The first public release is planned after the competitive feature set and release-readiness work described in the checklist are complete.
