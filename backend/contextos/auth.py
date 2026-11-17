"""Password authentication and revocable, CSRF-protected web sessions."""

import hashlib
import hmac
import os
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import psycopg
from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Response
from pydantic import BaseModel, Field

from .database import connection

router = APIRouter(prefix="/v1/auth", tags=["auth"])
COOKIE = "contextos_session"
SESSION_DAYS = 14


class Credentials(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=12, max_length=1024)


def normalize_email(value: str) -> str:
    email = value.strip().lower()
    if not re.fullmatch(r"[^@\s<>]+@[^@\s<>]+\.[^@\s<>]+", email):
        raise HTTPException(422, detail="Enter a valid email address")
    return email


def password_hash(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
    return f"scrypt$16384$8$1${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, n, r, p, salt, expected = encoded.split("$")
        if algorithm != "scrypt" or (n, r, p) != ("16384", "8", "1"):
            return False
        actual = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=2**14, r=8, p=1)
        return hmac.compare_digest(actual, bytes.fromhex(expected))
    except (ValueError, TypeError):
        return False


def token_hash(token: str) -> bytes:
    return hashlib.sha256(token.encode("utf-8")).digest()


def csrf_for_session(token: str) -> str:
    return hashlib.sha256(("contextos-csrf:" + token).encode("utf-8")).hexdigest()


def cookie_secure() -> bool:
    return os.environ.get("CONTEXT_OS_COOKIE_SECURE", "true").lower() != "false"


def start_session(db, response: Response, account_id: uuid.UUID) -> str:
    token = secrets.token_urlsafe(32)
    csrf = csrf_for_session(token)
    db.execute(
        "INSERT INTO sessions (id, account_id, token_hash, csrf_hash, expires_at) "
        "VALUES (%s, %s, %s, %s, %s)",
        (uuid.uuid4(), account_id, token_hash(token), token_hash(csrf),
         datetime.now(timezone.utc) + timedelta(days=SESSION_DAYS)),
    )
    response.set_cookie(
        COOKIE, token, max_age=SESSION_DAYS * 86400, httponly=True,
        secure=cookie_secure(), samesite="lax", path="/",
    )
    return csrf


def current_session(contextos_session: str | None = Cookie(default=None)) -> dict:
    if not contextos_session:
        raise HTTPException(401, detail="Sign in required")
    with connection() as db:
        row = db.execute(
            "SELECT s.id, s.account_id, s.csrf_hash, a.email FROM sessions s "
            "JOIN accounts a ON a.id = s.account_id "
            "WHERE s.token_hash = %s AND s.revoked_at IS NULL AND s.expires_at > now()",
            (token_hash(contextos_session),),
        ).fetchone()
    if row is None:
        raise HTTPException(401, detail="Session expired")
    return row


def write_session(
    session: dict = Depends(current_session),
    x_csrf_token: str | None = Header(default=None),
) -> dict:
    if not x_csrf_token or not hmac.compare_digest(
        token_hash(x_csrf_token), bytes(session["csrf_hash"])
    ):
        raise HTTPException(403, detail="Invalid CSRF token")
    return session


@router.post("/register", status_code=201)
def register(credentials: Credentials, response: Response) -> dict:
    email = normalize_email(credentials.email)
    account_id = uuid.uuid4()
    with connection() as db:
        try:
            db.execute(
                "INSERT INTO accounts (id, email, password_hash) VALUES (%s, %s, %s)",
                (account_id, email, password_hash(credentials.password)),
            )
        except psycopg.errors.UniqueViolation as exc:
            raise HTTPException(409, detail="An account with this email exists") from exc
        csrf = start_session(db, response, account_id)
    return {"data": {"id": account_id, "email": email, "csrf_token": csrf}, "error": None}


@router.post("/login")
def login(credentials: Credentials, response: Response) -> dict:
    with connection() as db:
        row = db.execute(
            "SELECT id, email, password_hash FROM accounts WHERE email = %s",
            (normalize_email(credentials.email),),
        ).fetchone()
        if row is None or not verify_password(credentials.password, row["password_hash"]):
            raise HTTPException(401, detail="Invalid email or password")
        csrf = start_session(db, response, row["id"])
    return {"data": {"id": row["id"], "email": row["email"], "csrf_token": csrf}, "error": None}


@router.get("/session")
def session_info(
    session: dict = Depends(current_session),
    contextos_session: str = Cookie(),
) -> dict:
    csrf = csrf_for_session(contextos_session)
    return {"data": {"id": session["account_id"], "email": session["email"], "csrf_token": csrf}, "error": None}


@router.post("/logout")
def logout(response: Response, session: dict = Depends(write_session)) -> dict:
    with connection() as db:
        db.execute("UPDATE sessions SET revoked_at = now() WHERE id = %s", (session["id"],))
    response.delete_cookie(COOKIE, path="/", secure=cookie_secure(), samesite="lax")
    return {"data": {"signed_out": True}, "error": None}
