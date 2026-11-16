"""Environment-backed settings. Never provide a production database fallback."""

import os


def database_url() -> str:
    value = os.environ.get("CONTEXT_OS_DATABASE_URL", "").strip()
    if not value:
        raise RuntimeError("CONTEXT_OS_DATABASE_URL is required for the PostgreSQL API")
    if not value.startswith(("postgresql://", "postgres://")):
        raise RuntimeError("CONTEXT_OS_DATABASE_URL must be a PostgreSQL URL")
    return value
