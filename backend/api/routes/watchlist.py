"""Watchlist API routes.

PATCH /api/searches/{id}/watchlist  — toggle watchlist_mode on/off
GET  /api/searches/watchlist        — list all watchlist searches

IMPORTANT: This router must be registered in main.py BEFORE searches_router
to prevent the /{search_id} path parameter from capturing the literal
"watchlist" segment.
"""
from datetime import datetime, timezone
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.database import get_db
from shared.models.search import SavedSearch
from shared.schemas.search import SearchResponse

log = structlog.get_logger()

router = APIRouter(prefix="/api/searches", tags=["watchlist"])


class WatchlistToggle(BaseModel):
    watchlist_mode: bool


@router.get("/watchlist", response_model=list[SearchResponse])
async def list_watchlist(db: AsyncSession = Depends(get_db)):
    """Return all searches that have watchlist_mode=True."""
    result = await db.execute(
        select(SavedSearch).where(
            SavedSearch.watchlist_mode == True,  # noqa: E712
            SavedSearch.is_active == True,       # noqa: E712
        )
    )
    return result.scalars().all()


@router.patch("/{search_id}/watchlist", response_model=SearchResponse)
async def toggle_watchlist(
    search_id: int,
    body: WatchlistToggle,
    db: AsyncSession = Depends(get_db),
):
    """Enable or disable watchlist mode for a saved search."""
    search = await db.get(SavedSearch, search_id)
    if not search:
        raise HTTPException(status_code=404, detail="Search not found")

    search.watchlist_mode = body.watchlist_mode
    search.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(search)

    log.info(
        "watchlist.toggled",
        search_id=search_id,
        watchlist_mode=body.watchlist_mode,
    )
    return search
