from datetime import datetime
from typing import Optional
from sqlalchemy import String, DateTime, Integer
from sqlalchemy.orm import Mapped, mapped_column
from pgvector.sqlalchemy import Vector
from shared.database import Base


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    canonical_title: Mapped[str] = mapped_column(String(512))
    category: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    embedding: Mapped[Optional[list[float]]] = mapped_column(Vector(384), nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    dedup_group_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    # pgvector ivfflat index created in Alembic migration
