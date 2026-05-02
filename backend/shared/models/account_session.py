from datetime import datetime
from enum import Enum
from typing import Optional
from sqlalchemy import String, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB, ENUM as PgEnum
from sqlalchemy.orm import Mapped, mapped_column
from shared.database import Base


class SessionStatus(str, Enum):
    ACTIVE = "active"
    EXPIRED = "expired"
    BANNED = "banned"
    NEEDS_REFRESH = "needs_refresh"

    def __str__(self) -> str:
        return self.value


class AccountSession(Base):
    __tablename__ = "account_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[str] = mapped_column(String(32), ForeignKey("sources.id"), index=True)
    label: Mapped[str] = mapped_column(String(128))
    # cookies stored encrypted with Fernet (key from FERNET_KEY env)
    cookies: Mapped[dict] = mapped_column(JSONB, default=dict)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[SessionStatus] = mapped_column(
        PgEnum(SessionStatus, name="session_status", create_type=False, values_callable=lambda x: [e.value for e in x]),
        default=SessionStatus.ACTIVE,
        index=True,
    )
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_health_check_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
