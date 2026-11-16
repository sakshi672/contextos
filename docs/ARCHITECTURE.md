# Architecture notes

The current workspace began without application code. The initial implementation is deliberately local so the source and memory workflow can be developed before opening access to public users.

The planned public architecture, capture contract, limits, and data model are in [PHASE_0_SPEC.md](PHASE_0_SPEC.md). This file describes the **current implemented slice**.

## Current stack

- React and TypeScript with Vite for the web app.
- Python standard-library HTTP API for the local development server.
- SQLite with FTS5 for persisted records and keyword search.
- No paid service, AI provider, or remote storage dependency in the current slice.

The browser extension will be a separate Manifest V3 client calling the same API contract as the web app. Before hosted deployment, the server needs account isolation, production authentication, upload storage, background extraction, rate limits, and a production-ready service boundary. The roadmap records those as required work, not optional polish.

## Current data flow

The UI sends JSON to `/api/memories`. The API validates a note or HTTP(S) link and writes it to `memories`. A corresponding FTS5 row stores searchable title, note, and URL text. Edits update both rows; deletion removes both. The local database path defaults to `data/context.db`.

The full memory model will expand to retain original files and extracted content separately, capture provenance for each field, support projects and relationships, and distinguish user content from generated content. The current table is not yet the final public schema.
