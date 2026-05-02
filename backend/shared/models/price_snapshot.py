from datetime import datetime
from decimal import Decimal
from typing import Optional
from sqlalchemy import Integer, Numeric, String, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from shared.database import Base


class PriceSnapshot(Base):
    __tablename__ = "price_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("listings.id"), index=True)
    price_thb: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    price_original: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(3), default="THB")
    fx_rate: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 6), nullable=True)
    scraped_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    scrape_run_id: Mapped[Optional[int]] = mapped_column(ForeignKey("scrape_runs.id"), nullable=True)
    # Composite index (listing_id, scraped_at DESC) created in Alembic migration
    # Table partitioned by month via Alembic migration for efficient retention
