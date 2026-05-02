from datetime import datetime, timezone
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.database import get_db
from shared.models.account_session import AccountSession, SessionStatus
from shared.config import get_settings

log = structlog.get_logger()
router = APIRouter(prefix="/api/sessions", tags=["sessions"])

settings = get_settings()


class SessionResponse(BaseModel):
    id: int
    source_id: str
    label: str
    expires_at: Optional[datetime]
    status: str
    last_used_at: Optional[datetime]
    last_health_check_at: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True


class SessionCreate(BaseModel):
    source_id: str
    label: str
    cookies_json: str


def _encrypt_cookies(cookies_json: str) -> dict:
    """Encrypt cookies_json string with Fernet if key is set, otherwise store plaintext."""
    fernet_key = settings.fernet_key
    if fernet_key:
        from cryptography.fernet import Fernet
        f = Fernet(fernet_key.encode() if isinstance(fernet_key, str) else fernet_key)
        encrypted = f.encrypt(cookies_json.encode()).decode()
        return {"_encrypted": encrypted}
    # Plaintext fallback (dev / no key configured)
    return {"_plaintext": cookies_json}


def _session_to_response(session: AccountSession) -> SessionResponse:
    return SessionResponse(
        id=session.id,
        source_id=session.source_id,
        label=session.label,
        expires_at=session.expires_at,
        status=str(session.status),
        last_used_at=session.last_used_at,
        last_health_check_at=session.last_health_check_at,
        created_at=session.created_at,
    )


@router.get("", response_model=list[SessionResponse])
async def list_sessions(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(AccountSession))
    return [_session_to_response(s) for s in result.scalars().all()]


@router.post("", response_model=SessionResponse, status_code=201)
async def create_session(body: SessionCreate, db: AsyncSession = Depends(get_db)):
    cookies_payload = _encrypt_cookies(body.cookies_json)
    session = AccountSession(
        source_id=body.source_id,
        label=body.label,
        cookies=cookies_payload,
        status=SessionStatus.ACTIVE,
        created_at=datetime.now(timezone.utc),
    )
    db.add(session)
    await db.flush()
    log.info("session.created", session_id=session.id, source_id=body.source_id, label=body.label)
    return _session_to_response(session)


@router.delete("/{session_id}", status_code=204)
async def delete_session(session_id: int, db: AsyncSession = Depends(get_db)):
    session = await db.get(AccountSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    await db.delete(session)
    log.info("session.deleted", session_id=session_id)
