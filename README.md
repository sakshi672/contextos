# Context OS

Context OS is being built as a web app and a browser extension. The current implementation is the first **local development slice**: a light-theme library that saves links and notes, persists them in SQLite, and retrieves them with keyword search. The complete product scope and sequence are in [ROADMAP.md](ROADMAP.md) and [IMPLEMENTATION_CHECKLIST.md](IMPLEMENTATION_CHECKLIST.md).

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

The first slice stores link metadata entered by the user; it does not yet fetch article content. Uploads, browser extension capture, projects, account sign-in, export, semantic search, graph, timeline, and AI are tracked in the checklist. No public deployment is planned until the complete product passes the release phase.
