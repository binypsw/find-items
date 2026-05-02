from datetime import datetime, timezone
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.database import get_db
from shared.models.search import SavedSearch
from shared.schemas.search import RunResponse, SearchCreate, SearchResponse

log = structlog.get_logger()
router = APIRouter(prefix="/api/searches", tags=["searches"])


@router.get("", response_model=list[SearchResponse])
async def list_searches(active: Optional[bool] = None, db: AsyncSession = Depends(get_db)):
    stmt = select(SavedSearch)
    if active is not None:
        stmt = stmt.where(SavedSearch.is_active == active)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.post("", response_model=SearchResponse, status_code=201)
async def create_search(body: SearchCreate, db: AsyncSession = Depends(get_db)):
    from shared.services.query_parser import parse_query as _parse_query

    now = datetime.now(timezone.utc)
    search = SavedSearch(
        name=body.name,
        raw_query=body.raw_query,
        schedule_cron=body.schedule_cron,
        source_filter=body.source_filter,
        max_price=body.max_price,
        min_price=body.min_price,
        is_active=True,
        created_at=now,
        updated_at=now,
    )

    try:
        parsed = await _parse_query(body.raw_query)
        search.parsed_query = parsed
    except Exception as exc:
        log.warning("search.parse_query_failed", error=str(exc))

    db.add(search)
    await db.flush()
    log.info("search.created", search_id=search.id, name=body.name)
    return search


@router.get("/{search_id}", response_model=SearchResponse)
async def get_search(search_id: int, db: AsyncSession = Depends(get_db)):
    search = await db.get(SavedSearch, search_id)
    if not search:
        raise HTTPException(status_code=404, detail="Search not found")
    return search


@router.delete("/{search_id}", status_code=204)
async def delete_search(search_id: int, db: AsyncSession = Depends(get_db)):
    search = await db.get(SavedSearch, search_id)
    if not search:
        raise HTTPException(status_code=404, detail="Search not found")
    await db.delete(search)


class RunRequest(BaseModel):
    source_filter: Optional[list[str]] = None


@router.post("/{search_id}/run", response_model=RunResponse)
async def trigger_run(
    search_id: int,
    body: RunRequest = RunRequest(),
    db: AsyncSession = Depends(get_db),
):
    source_filter = body.source_filter
    from worker.tasks.scrape_task import run_search
    from shared.models.source import Source
    from sqlalchemy import select

    search = await db.get(SavedSearch, search_id)
    if not search:
        raise HTTPException(status_code=404, detail="Search not found")

    # Determine which sources will run
    result = await db.execute(select(Source).where(Source.enabled == True))
    all_sources = result.scalars().all()
    source_ids = [s.id for s in all_sources if not source_filter or s.id in source_filter]

    if not source_ids:
        raise HTTPException(status_code=400, detail="No enabled sources available")

    task = run_search.apply_async(
        args=[search_id],
        kwargs={"source_filter": source_filter, "triggered_by": "manual"},
    )

    # Update last_run_at
    search.last_run_at = datetime.now(timezone.utc)
    search.updated_at = datetime.now(timezone.utc)

    log.info("search.run_triggered", search_id=search_id, task_id=task.id)
    return RunResponse(run_id=0, task_id=task.id, source_ids=source_ids)


@router.post("/parse")
async def parse_query(body: dict):
    """Preview LLM parsing of a raw query (no DB save)."""
    from shared.services.query_parser import parse_query as _parse_query

    raw = body.get("raw_query", "")
    return await _parse_query(raw)
