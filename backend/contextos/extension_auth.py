"""Short-lived pairing codes and revocable extension credentials."""

import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from .auth import token_hash, write_session
from .database import connection

router = APIRouter(prefix="/v1/extension", tags=["extension"])


class PairingExchange(BaseModel):
    code: str = Field(min_length=12, max_length=128)


def extension_session(authorization: str | None = Header(default=None)) -> dict:
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(401, detail="Connect the extension to your account")
    with connection() as db:
        row = db.execute("""SELECT c.id, c.account_id, a.email FROM extension_credentials c
            JOIN accounts a ON a.id = c.account_id
            WHERE c.token_hash = %s AND c.revoked_at IS NULL AND c.expires_at > now()""",
            (token_hash(token),)).fetchone()
        if row:
            db.execute("UPDATE extension_credentials SET last_used_at = now() WHERE id = %s", (row["id"],))
    if not row:
        raise HTTPException(401, detail="Extension connection expired; pair again")
    return row


@router.post("/pairings", status_code=201)
def create_pairing(session: dict = Depends(write_session)) -> dict:
    code = secrets.token_urlsafe(18)
    with connection() as db:
        db.execute("DELETE FROM extension_pairings WHERE account_id = %s AND used_at IS NULL", (session["account_id"],))
        db.execute("INSERT INTO extension_pairings (id, account_id, code_hash, expires_at) VALUES (%s,%s,%s,%s)",
                   (uuid.uuid4(), session["account_id"], token_hash(code),
                    datetime.now(timezone.utc) + timedelta(minutes=10)))
    return {"data": {"code": code, "expires_in_seconds": 600}, "error": None}


@router.post("/tokens")
def exchange_pairing(payload: PairingExchange) -> dict:
    with connection() as db:
        pairing = db.execute("""SELECT id, account_id FROM extension_pairings
            WHERE code_hash = %s AND used_at IS NULL AND expires_at > now() FOR UPDATE""",
            (token_hash(payload.code),)).fetchone()
        if pairing is None:
            raise HTTPException(401, detail="Pairing code is invalid or expired")
        db.execute("UPDATE extension_pairings SET used_at = now() WHERE id = %s", (pairing["id"],))
        token = secrets.token_urlsafe(32)
        db.execute("INSERT INTO extension_credentials (id, account_id, token_hash) VALUES (%s,%s,%s)",
                   (uuid.uuid4(), pairing["account_id"], token_hash(token)))
        email = db.execute("SELECT email FROM accounts WHERE id = %s", (pairing["account_id"],)).fetchone()["email"]
    return {"data": {"token": token, "email": email}, "error": None}


@router.get("/session")
def extension_info(session: dict = Depends(extension_session)) -> dict:
    return {"data": {"email": session["email"]}, "error": None}


@router.post("/revoke")
def revoke_extension(session: dict = Depends(extension_session)) -> dict:
    with connection() as db:
        db.execute("UPDATE extension_credentials SET revoked_at = now() WHERE id = %s", (session["id"],))
    return {"data": {"revoked": True}, "error": None}
