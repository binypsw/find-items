from datetime import datetime
from typing import Optional
from sqlalchemy import String, Boolean, DateTime, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from shared.database import Base


class SavedSearch(Base):
    __tablename__ = "saved_searches"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(256))
    raw_query: Mapped[str] = mapped_column(Text)
    parsed_query: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    schedule_cron: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    max_price: Mapped[Optional[int]] = mapped_column(nullable=True)
    min_price: Mapped[Optional[int]] = mapped_column(nullable=True)
    condition: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    location: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    source_filter: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    last_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    owner_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    watchlist_mode: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    last_watchlist_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
