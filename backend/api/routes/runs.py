from datetime import datetime
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.database import get_db
from shared.models.scrape_run import ScrapeRun

log = structlog.get_logger()
router = APIRouter(tags=["runs"])


class RunDetailResponse(BaseModel):
    id: int
    search_id: Optional[int]
    source_id: str
    started_at: datetime
    finished_at: Optional[datetime]
    status: str
    items_found: int
    items_new: int
    items_updated: int
    errors: Optional[dict]
    api_credits_used: int

    class Config:
        from_attributes = True


def _run_to_response(run: ScrapeRun) -> RunDetailResponse:
    return RunDetailResponse(
        id=run.id,
        search_id=run.search_id,
        source_id=run.source_id,
        started_at=run.started_at,
        finished_at=run.finished_at,
        status=str(run.status),
        items_found=run.items_found,
        items_new=run.items_new,
        items_updated=run.items_updated,
        errors=run.errors,
        api_credits_used=run.api_credits_used,
    )


@router.get("/api/runs/{run_id}", response_model=RunDetailResponse)
async def get_run(run_id: int, db: AsyncSession = Depends(get_db)):
    run = await db.get(ScrapeRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return _run_to_response(run)


@router.get("/api/searches/{search_id}/runs", response_model=list[RunDetailResponse])
async def list_runs_for_search(
    search_id: int,
    limit: int = Query(default=10, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ScrapeRun)
        .where(ScrapeRun.search_id == search_id)
        .order_by(ScrapeRun.started_at.desc())
        .limit(limit)
    )
    runs = result.scalars().all()
    return [_run_to_response(r) for r in runs]
