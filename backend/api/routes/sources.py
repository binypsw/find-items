from datetime import datetime
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.database import get_db
from shared.models.source import Source

log = structlog.get_logger()
router = APIRouter(prefix="/api/sources", tags=["sources"])


class SourceResponse(BaseModel):
    id: str
    name: str
    base_url: str
    tier: str
    enabled: bool
    health_status: str
    last_success_at: Optional[datetime]
    monthly_credit_budget: int
    credits_used_this_month: int
    api_provider: Optional[str]

    class Config:
        from_attributes = True


class SourceUpdate(BaseModel):
    enabled: Optional[bool] = None
    monthly_credit_budget: Optional[int] = None


@router.get("", response_model=list[SourceResponse])
async def list_sources(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Source))
    return result.scalars().all()


@router.patch("/{source_id}", response_model=SourceResponse)
async def update_source(
    source_id: str,
    body: SourceUpdate,
    db: AsyncSession = Depends(get_db),
):
    source = await db.get(Source, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    if body.enabled is not None:
        source.enabled = body.enabled
    if body.monthly_credit_budget is not None:
        source.monthly_credit_budget = body.monthly_credit_budget

    log.info("source.updated", source_id=source_id, enabled=body.enabled, budget=body.monthly_credit_budget)
    return source
