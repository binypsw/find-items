from datetime import datetime
from typing import Optional
from sqlalchemy import String, Boolean, Integer, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from shared.database import Base


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)  # "shopee", "lazada", ...
    name: Mapped[str] = mapped_column(String(128))
    base_url: Mapped[str] = mapped_column(String(256))
    tier: Mapped[str] = mapped_column(String(16))  # "direct" | "browserless" | "managed_api"
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    health_status: Mapped[str] = mapped_column(String(16), default="unknown")
    last_success_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    monthly_credit_budget: Mapped[int] = mapped_column(Integer, default=0)
    credits_used_this_month: Mapped[int] = mapped_column(Integer, default=0)
    api_provider: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)  # "scrapfly" | "zenrows" | None
