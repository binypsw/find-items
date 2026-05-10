import json
from typing import Optional

import structlog
from cryptography.fernet import Fernet
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from shared.config import get_settings
from shared.models.account_session import AccountSession, SessionStatus

log = structlog.get_logger()


class CookieStore:
    """Encrypted cookie storage for authenticated sources (e.g. Facebook Marketplace).

    Cookies are encrypted with Fernet before writing to DB and decrypted on read.
    The Fernet key is loaded from FERNET_KEY env var.
    """

    def __init__(self, db: AsyncSession, fernet_key: str | None = None):
        settings = get_settings()
        key = fernet_key or settings.fernet_key
        if not key:
            raise ValueError("FERNET_KEY is not set — required for cookie storage")
        self._fernet = Fernet(key.encode() if isinstance(key, str) else key)
        self._db = db

    def _encrypt(self, cookies: list[dict]) -> bytes:
        return self._fernet.encrypt(json.dumps(cookies).encode())

    def _decrypt(self, encrypted: bytes) -> list[dict]:
        return json.loads(self._fernet.decrypt(encrypted))

    async def get_active(self, source_id: str) -> Optional[list[dict]]:
        """Return decrypted cookies for the first active session of source_id."""
        result = await self._db.execute(
            select(AccountSession).where(
                AccountSession.source_id == source_id,
                AccountSession.status == SessionStatus.ACTIVE,
            ).limit(1)
        )
        session = result.scalar_one_or_none()
        if not session:
            log.debug("cookie_store.no_active_session", source_id=source_id)
            return None
        try:
            raw = session.cookies.get("_encrypted")
            if raw:
                return self._decrypt(raw.encode())
            # Fallback: unencrypted (legacy / dev)
            return session.cookies.get("cookies", [])
        except Exception as e:
            log.error("cookie_store.decrypt_fail", source_id=source_id, error=str(e))
            return None

    async def store(self, source_id: str, label: str, cookies: list[dict]) -> AccountSession:
        """Encrypt and persist a new session's cookies."""
        from datetime import datetime, timezone

        encrypted = self._encrypt(cookies).decode()
        session = AccountSession(
            source_id=source_id,
            label=label,
            cookies={"_encrypted": encrypted},
            status=SessionStatus.ACTIVE,
            created_at=datetime.now(timezone.utc),
        )
        self._db.add(session)
        await self._db.flush()
        log.info("cookie_store.stored", source_id=source_id, label=label, session_id=session.id)
        return session
