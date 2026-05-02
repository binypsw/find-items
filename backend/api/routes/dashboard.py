from datetime import datetime, timezone, timedelta
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.database import get_db
from shared.models.listing import Listing
from shared.models.price_snapshot import PriceSnapshot
from shared.models.scrape_run import ScrapeRun
from api.routes.listings import ListingResponse, _to_response

log = structlog.get_logger()
router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


class RankedListingResponse(ListingResponse):
    score: float
    rank: int
    price_change_7d_pct: Optional[float]


@router.get("/{search_id}/top", response_model=list[RankedListingResponse])
async def get_top_listings(
    search_id: int,
    limit: int = Query(default=10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    # Resolve listing IDs for this search via ScrapeRun -> PriceSnapshot
    run_result = await db.execute(
        select(ScrapeRun.id).where(ScrapeRun.search_id == search_id)
    )
    run_ids = [r for (r,) in run_result.all()]
    if not run_ids:
        return []

    snap_result = await db.execute(
        select(PriceSnapshot.listing_id)
        .where(PriceSnapshot.scrape_run_id.in_(run_ids))
        .distinct()
    )
    listing_ids = [r for (r,) in snap_result.all()]
    if not listing_ids:
        return []

    # Fetch active listings
    result = await db.execute(
        select(Listing).where(
            Listing.id.in_(listing_ids),
            Listing.status == "active",
        )
    )
    listings = result.scalars().all()
    if not listings:
        return []

    # Compute price normalization bounds
    prices = [float(l.current_price_thb) for l in listings]
    min_price = min(prices)
    max_price = max(prices)
    price_range = max_price - min_price if max_price != min_price else 1.0

    # Fetch 7-day-ago snapshots for all listing ids in one query
    cutoff_7d = datetime.now(timezone.utc) - timedelta(days=7)
    snap7_result = await db.execute(
        select(PriceSnapshot)
        .where(
            PriceSnapshot.listing_id.in_(listing_ids),
            PriceSnapshot.scraped_at <= cutoff_7d,
        )
        .order_by(PriceSnapshot.listing_id, PriceSnapshot.scraped_at.desc())
    )
    all_snaps_7d = snap7_result.scalars().all()

    # Keep only the most-recent snapshot at-or-before 7d cutoff per listing
    snap7_by_listing: dict[int, float] = {}
    for snap in all_snaps_7d:
        if snap.listing_id not in snap7_by_listing:
            snap7_by_listing[snap.listing_id] = float(snap.price_thb)

    # Score and rank
    scored: list[tuple[float, Listing]] = []
    for listing in listings:
        price = float(listing.current_price_thb)
        score = 100.0

        # Condition bonus
        if listing.condition == "new":
            score += 20
        elif listing.condition == "used":
            score += 10

        # Price rank: lower price → higher score (up to +30)
        normalized_price_rank = 1.0 - (price - min_price) / price_range  # 1=cheapest, 0=most expensive
        score += normalized_price_rank * 30

        # Volatile price penalty
        if listing.price_change_count > 0:
            score -= 5

        # High sold count bonus
        seller = listing.seller_payload or {}
        if (seller.get("sold_count") or 0) > 100:
            score += 5

        scored.append((score, listing))

    # Sort by score descending
    scored.sort(key=lambda x: x[0], reverse=True)

    # Build response with rank and 7d price change
    response: list[RankedListingResponse] = []
    for rank_idx, (score, listing) in enumerate(scored[:limit], start=1):
        current_price = float(listing.current_price_thb)
        price_7d = snap7_by_listing.get(listing.id)
        if price_7d is not None and price_7d != 0:
            price_change_7d_pct = ((current_price - price_7d) / price_7d) * 100
        else:
            price_change_7d_pct = None

        base = _to_response(listing)
        response.append(
            RankedListingResponse(
                **base.model_dump(),
                score=round(score, 2),
                rank=rank_idx,
                price_change_7d_pct=round(price_change_7d_pct, 2) if price_change_7d_pct is not None else None,
            )
        )

    return response
