"""Private filesystem object storage for local development."""

import os
import uuid
from pathlib import Path


def root() -> Path:
    configured = os.environ.get("CONTEXT_OS_STORAGE_ROOT")
    path = Path(configured) if configured else Path(__file__).resolve().parents[2] / "data" / "uploads"
    return path.resolve()


def object_key(account_id: uuid.UUID, memory_id: uuid.UUID, asset_id: uuid.UUID) -> str:
    return f"{account_id}/{memory_id}/{asset_id}"


def path_for(key: str) -> Path:
    parts = key.split("/")
    if len(parts) != 3:
        raise ValueError("Invalid object key")
    normalized = [str(uuid.UUID(part)) for part in parts]
    path = root().joinpath(*normalized)
    if not path.is_relative_to(root()):
        raise ValueError("Object key escapes storage root")
    return path


def delete(key: str) -> None:
    path_for(key).unlink(missing_ok=True)
