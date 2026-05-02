from datetime import datetime
from enum import Enum
from typing import Optional
from sqlalchemy import String, Integer, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB, ENUM as PgEnum
from sqlalchemy.orm import Mapped, mapped_column
from shared.database import Base


class ScrapeRunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

    def __str__(self) -> str:
        return self.value


class ScrapeRun(Base):
    __tablename__ = "scrape_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    search_id: Mapped[Optional[int]] = mapped_column(ForeignKey("saved_searches.id"), nullable=True, index=True)
    source_id: Mapped[str] = mapped_column(String(32), ForeignKey("sources.id"), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[ScrapeRunStatus] = mapped_column(
        PgEnum(ScrapeRunStatus, name="scrape_run_status", create_type=False, values_callable=lambda x: [e.value for e in x]),
        default=ScrapeRunStatus.PENDING,
        index=True,
    )
    items_found: Mapped[int] = mapped_column(Integer, default=0)
    items_new: Mapped[int] = mapped_column(Integer, default=0)
    items_updated: Mapped[int] = mapped_column(Integer, default=0)
    errors: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    api_credits_used: Mapped[int] = mapped_column(Integer, default=0)
