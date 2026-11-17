"""Local-only setup and commands for the Docker PostgreSQL instance."""

import argparse
import os
import secrets
from pathlib import Path

ENV_FILE = Path(__file__).resolve().parents[1] / ".env"


def init_env() -> Path:
    password = secrets.token_hex(24)
    url = f"postgresql://contextos:{password}@127.0.0.1:5432/contextos"
    # Exclusive creation keeps an existing database password and URL intact.
    with ENV_FILE.open("x", encoding="utf-8") as file:
        file.write(f"CONTEXT_OS_DB_PASSWORD={password}\n")
        file.write(f"CONTEXT_OS_DATABASE_URL={url}\n")
    return ENV_FILE


def load_env() -> None:
    values = {}
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        if not separator or key not in {"CONTEXT_OS_DB_PASSWORD", "CONTEXT_OS_DATABASE_URL"}:
            raise ValueError("Invalid backend/.env format; expected only local database settings")
        values[key] = value
    if not values.get("CONTEXT_OS_DATABASE_URL"):
        raise ValueError("Missing CONTEXT_OS_DATABASE_URL in backend/.env")
    os.environ["CONTEXT_OS_DATABASE_URL"] = values["CONTEXT_OS_DATABASE_URL"]
    # Local HTTP is loopback-only. Hosted deployments keep secure cookies on.
    os.environ["CONTEXT_OS_COOKIE_SECURE"] = "false"


def main():
    parser = argparse.ArgumentParser(description="Local Docker PostgreSQL setup")
    parser.add_argument("command", choices=("init", "migrate", "serve", "worker"))
    args = parser.parse_args()
    if args.command == "init":
        try:
            path = init_env()
        except FileExistsError:
            parser.error("backend/.env already exists; keeping its current password")
        print(f"Created {path}. Use it with docker compose --env-file backend/.env.")
        return
    load_env()
    if args.command == "migrate":
        from .migrate import migrate

        print("Applied:", ", ".join(migrate()) or "none")
    elif args.command == "serve":
        import uvicorn

        uvicorn.run("backend.contextos.main:app", host="127.0.0.1", port=8766)
    else:
        from .worker import main as run_worker

        run_worker()


if __name__ == "__main__":
    main()
