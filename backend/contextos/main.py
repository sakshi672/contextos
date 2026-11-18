"""Versioned FastAPI entry point for the PostgreSQL-backed web app."""

from fastapi import FastAPI, HTTPException, Request
import psycopg

from .database import connection
from .auth import router as auth_router
from .memories import router as memories_router
from .uploads import router as uploads_router
from .exports import router as exports_router
from .imports import router as imports_router
from .recovery import router as recovery_router
from .extension_auth import router as extension_router
from .captures import router as captures_router

app = FastAPI(title="Context OS API", version="0.1.0", docs_url=None, redoc_url=None)
app.include_router(auth_router)
app.include_router(memories_router)
app.include_router(uploads_router)
app.include_router(exports_router)
app.include_router(imports_router)
app.include_router(recovery_router)
app.include_router(extension_router)
app.include_router(captures_router)


@app.middleware("http")
async def private_response(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/v1/"):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/v1/health/live", tags=["health"])
def liveness() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/v1/health/ready", tags=["health"])
def readiness() -> dict[str, str]:
    try:
        with connection() as db:
            db.execute("SELECT 1")
    except (psycopg.Error, OSError, RuntimeError) as exc:
        raise HTTPException(status_code=503, detail="Database unavailable") from exc
    return {"status": "ok"}
