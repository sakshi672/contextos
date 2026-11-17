# Context OS

Context OS is a personal memory system for capturing, connecting, and finding information across sources and projects, including when the user remembers only partial clues. The intended first release is a web app and browser extension with source-preserving capture, project memory, an explainable knowledge graph, hybrid retrieval, and a source-grounded assistant. The current implementation is the first **local development slice**: a light-theme library with account sign-in that saves links and notes in PostgreSQL. The complete product scope and sequence are in [ROADMAP.md](ROADMAP.md) and [IMPLEMENTATION_CHECKLIST.md](IMPLEMENTATION_CHECKLIST.md).

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
6. Start the extraction and file-cleanup worker in another terminal: `.venv\Scripts\python -m backend.contextos.local_db worker`.
7. Start the web app in a third terminal: `npm.cmd run dev` on Windows or `npm run dev` elsewhere.
8. Open `http://127.0.0.1:5173/` and create a local account.

The FastAPI service listens only on `127.0.0.1:8766`; Vite forwards `/v1` calls to it. New account and memory data is stored in PostgreSQL's named Docker volume and persists across restarts. `data/context.db` and `data/legacy-snapshot.zip` are retained as local backups from the SQLite prototype; the source had zero memories at cutover. Do not expose the development API to the internet; recovery, rate limits, and release security checks remain on the checklist.

See the [FastAPI/PostgreSQL backend notes](backend/README.md) for API and database details. The older `server/` SQLite API is kept only for snapshot and regression reference; the running web app uses PostgreSQL.

## Verify

- Backend workflow tests: `python -m unittest discover -s tests -v`
- Frontend type check and production build: `npm.cmd run build` (or `npm run build`)

Current manual flow: register, create a link or note, or upload a UTF-8 TXT/Markdown file. Uploaded documents move from pending to ready when the worker extracts their text. Open a document to view the extracted text or download the private original. Sort, filter, and page through the Library. Use **Export your data** to download an account-scoped ZIP and **Import data** to restore it or import browser bookmark HTML. Reload and sign back in to check PostgreSQL persistence. For local password recovery, use **Forgot password?** and open the newest link for your account in `data/recovery-outbox/`.

## Current limits

The current web app stores link metadata entered by the user; it does not yet fetch article content. Only TXT and Markdown uploads are supported so far. PDF, DOCX, images, browser extension capture, projects, semantic search, graph, timeline, and AI are tracked in the checklist. Hosted email verification, abuse controls, and release security checks are also outstanding. The first public release is planned after the competitive feature set and release-readiness work described in the checklist are complete.
