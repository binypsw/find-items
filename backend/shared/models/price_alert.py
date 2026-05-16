from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import ARRAY, TEXT
from sqlalchemy.orm import Mapped, mapped_column

from shared.database import Base


class PriceAlert(Base):
    __tablename__ = "price_alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("listings.id"), index=True)
    # comparison="lte": trigger when price <= target_price (absolute THB value)
    # comparison="pct_drop": trigger when drop% >= target_price (target_price = threshold %)
    target_price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    comparison: Mapped[str] = mapped_column(String(16))  # "lte" | "pct_drop"
    notify_channels: Mapped[list] = mapped_column(ARRAY(TEXT), default=list)  # ["discord"]
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    triggered_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
