from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional
from sqlalchemy import String, Numeric, Integer, DateTime, ForeignKey, UniqueConstraint, ARRAY
from sqlalchemy.dialects.postgresql import JSONB, ENUM as PgEnum
from sqlalchemy.orm import Mapped, mapped_column
from shared.database import Base


class ListingStatus(str, Enum):
    ACTIVE = "active"
    SOLD = "sold"
    DELETED = "deleted"
    STALE = "stale"
    ERROR = "error"

    def __str__(self) -> str:
        return self.value


class Listing(Base):
    __tablename__ = "listings"

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[Optional[int]] = mapped_column(ForeignKey("products.id"), nullable=True, index=True)
    source_id: Mapped[str] = mapped_column(String(32), ForeignKey("sources.id"), index=True)
    external_id: Mapped[str] = mapped_column(String(128))
    url: Mapped[str] = mapped_column(String(2048), unique=True)
    title: Mapped[str] = mapped_column(String(512))
    description: Mapped[Optional[str]] = mapped_column(nullable=True)
    current_price_thb: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    price_original: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(3), default="THB")
    condition: Mapped[str] = mapped_column(String(16), default="unknown")
    seller_payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    location: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    image_urls: Mapped[list] = mapped_column(JSONB, default=list)
    spec_tokens: Mapped[list] = mapped_column(ARRAY(String), default=list)
    raw_payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    status: Mapped[ListingStatus] = mapped_column(
        PgEnum(ListingStatus, name="listing_status", create_type=False, values_callable=lambda x: [e.value for e in x]),
        default=ListingStatus.ACTIVE,
        index=True,
    )
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    consecutive_missing_count: Mapped[int] = mapped_column(Integer, default=0)
    next_poll_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    poll_interval_minutes: Mapped[int] = mapped_column(Integer, default=720)
    last_payload_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    price_change_count: Mapped[int] = mapped_column(Integer, default=0)

    __table_args__ = (
        UniqueConstraint("source_id", "external_id", name="uq_listing_source_external"),
        # GIN index on spec_tokens created in Alembic migration
    )
