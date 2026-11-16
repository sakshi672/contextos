# Context OS

Context OS is a personal memory system for capturing, connecting, and finding information across sources and projects, including when the user remembers only partial clues. The intended first release is a web app and browser extension with source-preserving capture, project memory, an explainable knowledge graph, hybrid retrieval, and a source-grounded assistant. The current implementation is the first **local development slice**: a light-theme library that saves links and notes, persists them in SQLite, and retrieves them with keyword search. The complete product scope and sequence are in [ROADMAP.md](ROADMAP.md) and [IMPLEMENTATION_CHECKLIST.md](IMPLEMENTATION_CHECKLIST.md).

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

Requirements: Node.js 22+, npm, and Python 3.13+.

1. Install frontend dependencies: `npm.cmd install` on Windows or `npm install` elsewhere.
2. Start the API in one terminal: `python -m server.app`.
3. Start the web app in another terminal: `npm.cmd run dev` on Windows or `npm run dev` elsewhere.
4. Open `http://127.0.0.1:5173/`.

The API listens only on `127.0.0.1:8765`. Vite forwards `/api` calls to it. Local data is stored in `data/context.db` and persists across restarts. Set `CONTEXT_OS_DB` to a different path if needed. Do not expose this development API to the internet; account isolation and production security are later checklist tasks.

## Verify

- Backend workflow tests: `python -m unittest discover -s tests -v`
- Frontend type check and production build: `npm.cmd run build` (or `npm run build`)

Current manual flow: create a link or note, search for words in its title, URL, or note, edit it, then delete it. Reload the page to check persistence.

## Current limits

The first slice stores link metadata entered by the user; it does not yet fetch article content. Uploads, browser extension capture, projects, account sign-in, export, semantic search, graph, timeline, and AI are tracked in the checklist. The first public release is planned after the competitive feature set and release-readiness work described in the checklist are complete.
