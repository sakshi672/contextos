"""One-time email recovery with local-development and SMTP delivery."""

import os
import secrets
import smtplib
import uuid
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from pathlib import Path

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field

from .auth import COOKIE, cookie_secure, normalize_email, password_hash, token_hash
from .database import connection

router = APIRouter(prefix="/v1/auth", tags=["auth"])
TOKEN_MINUTES = 30
LOCAL_OUTBOX = Path(__file__).resolve().parents[2] / "data" / "recovery-outbox"


class RecoveryRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)


class RecoveryReset(BaseModel):
    token: str = Field(min_length=32, max_length=256)
    password: str = Field(min_length=12, max_length=1024)


def delivery_mode() -> str:
    mode = os.environ.get("CONTEXT_OS_RECOVERY_DELIVERY", "").lower()
    if mode not in {"local", "smtp"}:
        raise HTTPException(503, detail="Account recovery is not configured")
    if mode == "local" and cookie_secure():
        raise HTTPException(503, detail="Local recovery is only available in local development")
    return mode


def recovery_link(token: str, mode: str) -> str:
    configured = os.environ.get("CONTEXT_OS_WEB_ORIGIN")
    if mode == "smtp" and not configured:
        raise HTTPException(503, detail="Recovery web origin is not configured")
    origin = (configured or "http://127.0.0.1:5173").rstrip("/")
    if not origin.startswith(("https://", "http://127.0.0.1:", "http://localhost:")):
        raise HTTPException(503, detail="Recovery web origin is not configured securely")
    return f"{origin}/#reset={token}"


def deliver(email: str, token: str, mode: str) -> None:
    link = recovery_link(token, mode)
    message = f"Reset your Context OS password within {TOKEN_MINUTES} minutes:\n\n{link}\n\nIf you did not request this, ignore it.\n"
    if mode == "local":
        LOCAL_OUTBOX.mkdir(parents=True, exist_ok=True)
        target = LOCAL_OUTBOX / f"{uuid.uuid4()}.txt"
        with target.open("x", encoding="utf-8") as out:
            out.write(f"To: {email}\n\n{message}")
        return
    host = os.environ.get("CONTEXT_OS_SMTP_HOST")
    sender = os.environ.get("CONTEXT_OS_SMTP_FROM")
    if not host or not sender:
        raise HTTPException(503, detail="Account recovery mail is not configured")
    mail = EmailMessage()
    mail["Subject"] = "Reset your Context OS password"
    mail["From"] = sender
    mail["To"] = email
    mail.set_content(message)
    port = int(os.environ.get("CONTEXT_OS_SMTP_PORT", "587"))
    with smtplib.SMTP(host, port, timeout=10) as smtp:
        smtp.starttls()
        username = os.environ.get("CONTEXT_OS_SMTP_USERNAME")
        if username:
            smtp.login(username, os.environ.get("CONTEXT_OS_SMTP_PASSWORD", ""))
        smtp.send_message(mail)


@router.post("/recover/request")
def request_recovery(payload: RecoveryRequest) -> dict:
    mode = delivery_mode()
    email = normalize_email(payload.email)
    # Unknown addresses and recently requested addresses receive the same answer.
    with connection() as db:
        account = db.execute("SELECT id, email FROM accounts WHERE email = %s FOR UPDATE", (email,)).fetchone()
        if account:
            recent = db.execute("""SELECT 1 FROM recovery_tokens WHERE account_id = %s
                AND used_at IS NULL AND expires_at > now() + interval '25 minutes' LIMIT 1""",
                (account["id"],)).fetchone()
            if not recent:
                token = secrets.token_urlsafe(32)
                db.execute("""INSERT INTO recovery_tokens (id, account_id, token_hash, expires_at)
                    VALUES (%s, %s, %s, %s)""", (uuid.uuid4(), account["id"], token_hash(token),
                    datetime.now(timezone.utc) + timedelta(minutes=TOKEN_MINUTES)))
                try:
                    deliver(account["email"], token, mode)
                except (OSError, smtplib.SMTPException) as exc:
                    raise HTTPException(503, detail="Recovery mail is temporarily unavailable") from exc
    return {"data": {"sent_if_account_exists": True}, "error": None}


@router.post("/recover/reset")
def reset_password(payload: RecoveryReset, response: Response) -> dict:
    with connection() as db:
        recovery = db.execute("""SELECT id, account_id FROM recovery_tokens
            WHERE token_hash = %s AND used_at IS NULL AND expires_at > now() FOR UPDATE""",
            (token_hash(payload.token),)).fetchone()
        if recovery is None:
            raise HTTPException(400, detail="Recovery link is invalid or expired")
        db.execute("UPDATE accounts SET password_hash = %s, email_verified_at = COALESCE(email_verified_at, now()), updated_at = now() WHERE id = %s",
                   (password_hash(payload.password), recovery["account_id"]))
        db.execute("UPDATE recovery_tokens SET used_at = now() WHERE account_id = %s AND used_at IS NULL",
                   (recovery["account_id"],))
        db.execute("UPDATE sessions SET revoked_at = now() WHERE account_id = %s AND revoked_at IS NULL",
                   (recovery["account_id"],))
    response.delete_cookie(COOKIE, path="/", secure=cookie_secure(), samesite="lax")
    return {"data": {"password_reset": True}, "error": None}
