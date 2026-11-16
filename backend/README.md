# Phase 1 PostgreSQL foundation

The web app now uses this FastAPI/PostgreSQL backend for account registration, login, logout, cookie sessions, CSRF checks, and account-scoped note/link memory CRUD. The legacy SQLite API and database are retained only as local backups and regression references. Account recovery, email verification, rate limits, broader ownership checks, and deployment controls are still required before public access.

## Local setup

1. Install and start [Docker Desktop for Windows](https://docs.docker.com/desktop/setup/install/windows-install/) with its Linux container backend.
2. Create a virtual environment: `python -m venv .venv`.
3. Install packages: `.venv\Scripts\python -m pip install -r backend\requirements.txt` on Windows.
4. Generate local database settings once: `.venv\Scripts\python -m backend.contextos.local_db init`. This creates ignored `backend/.env` with a random password. Do not run `init` again after the database has data.
5. Start PostgreSQL: `docker compose --env-file backend/.env up -d postgres`. The service binds only to `127.0.0.1:5432` and stores data in the named `contextos_pgdata` volume.
6. Apply migrations: `.venv\Scripts\python -m backend.contextos.local_db migrate`.
7. Start the API: `.venv\Scripts\python -m backend.contextos.local_db serve`.

Run `docker compose --env-file backend/.env ps` to see health status. `docker compose --env-file backend/.env down` stops the database but retains its named volume. The settings file and volume are tied together: changing the password in `backend/.env` does not change an existing PostgreSQL user's password. Hosted deployments instead supply `CONTEXT_OS_DATABASE_URL` through a secret store and run the direct migration/API entry points.

`/v1/health/live` checks the process; `/v1/health/ready` checks PostgreSQL connectivity. `POST /v1/auth/register`, `POST /v1/auth/login`, `GET /v1/auth/session`, and `POST /v1/auth/logout` manage a local account session. The first two return a CSRF token and set an HTTP-only session cookie; `GET /v1/auth/session` restores the session's CSRF token after page reload. Send that token in `X-CSRF-Token` for writes. `GET/POST /v1/memories` and `GET/PATCH/DELETE /v1/memories/{id}` handle owned note/link records. Responses use `{data, error}`. `local_db serve` permits cookies over loopback HTTP; hosted deployments default to secure cookies and must use HTTPS. OpenAPI is available programmatically through `app.openapi()`. The background worker entry point is `python -m backend.contextos.worker`; do not run it yet, because no extraction handler is registered or job producer is enabled.

Run `.venv\Scripts\python -m unittest discover -s tests -v` to exercise the legacy API, snapshot, and live PostgreSQL account-isolation workflow. The PostgreSQL test skips only when the local database settings or service are unavailable.

Before the SQLite prototype is retired, create a read-only snapshot with `python -m backend.contextos.legacy_export data/context.db data/legacy-snapshot.zip`. The command refuses to overwrite an existing snapshot and includes all prototype memory fields plus a checksum. This is a migration safeguard, not the final account export or a PostgreSQL import. An importer will be added and tested before account cutover. Keep the SQLite source until that import has been verified.
