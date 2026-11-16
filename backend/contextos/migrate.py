"""Apply ordered SQL migrations transactionally against PostgreSQL."""

from pathlib import Path

from .database import connection

MIGRATIONS = Path(__file__).resolve().parents[1] / "migrations"


def migrate() -> list[str]:
    applied = []
    with connection() as db:
        # A transaction-scoped lock prevents simultaneous API/worker deployments
        # from racing to apply the same schema version.
        db.execute("SELECT pg_advisory_xact_lock(509174201)")
        db.execute("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version text PRIMARY KEY,
                applied_at timestamptz NOT NULL DEFAULT now()
            )
        """)
        known = {row["version"] for row in db.execute("SELECT version FROM schema_migrations")}
        for path in sorted(MIGRATIONS.glob("[0-9][0-9][0-9][0-9]_*.sql")):
            if path.stem in known:
                continue
            db.execute(path.read_text(encoding="utf-8"), prepare=False)
            db.execute("INSERT INTO schema_migrations (version) VALUES (%s)", (path.stem,))
            applied.append(path.stem)
    return applied


if __name__ == "__main__":
    print("Applied:", ", ".join(migrate()) or "none")
