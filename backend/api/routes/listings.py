from datetime import datetime, timezone, timedelta
from typing import Literal, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.database import get_db
from shared.models.listing import Listing
from shared.models.price_snapshot import PriceSnapshot
from shared.models.scrape_run import ScrapeRun
from shared.services.seller_analyzer import (
    SellerRisk,
    extract_seller_signals,
    classify_seller_risk,
)

log = structlog.get_logger()
router = APIRouter(prefix="/api/listings", tags=["listings"])


class ListingResponse(BaseModel):
    id: int
    product_id: Optional[int]
    source_id: str
    external_id: str
    url: str
    title: str
    description: Optional[str]
    current_price_thb: float
    price_original: float
    currency: str
    condition: str
    seller_payload: dict
    location: Optional[str]
    image_urls: list[str]
    status: str
    first_seen_at: datetime
    last_seen_at: datetime
    next_poll_at: Optional[datetime]
    price_change_count: int

    class Config:
        from_attributes = True


class PaginatedListings(BaseModel):
    items: list[ListingResponse]
    total: int
    page: int
    page_size: int


def _to_response(listing: Listing) -> ListingResponse:
    return ListingResponse(
        id=listing.id,
        product_id=listing.product_id,
        source_id=listing.source_id,
        external_id=listing.external_id,
        url=listing.url,
        title=listing.title,
        description=listing.description,
        current_price_thb=float(listing.current_price_thb),
        price_original=float(listing.price_original),
        currency=listing.currency,
        condition=listing.condition,
        seller_payload=listing.seller_payload or {},
        location=listing.location,
        image_urls=listing.image_urls or [],
        status=str(listing.status),
        first_seen_at=listing.first_seen_at,
        last_seen_at=listing.last_seen_at,
        next_poll_at=listing.next_poll_at,
        price_change_count=listing.price_change_count,
    )


@router.get("", response_model=PaginatedListings)
async def list_listings(
    search_id: Optional[int] = None,
    source_id: Optional[str] = None,
    status: Optional[str] = "active",
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    condition: Optional[str] = None,
    location: Optional[str] = None,
    sort: Optional[str] = Query(default="newest", pattern="^(price_asc|price_desc|newest|oldest)$"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Listing)

    # Filter by search_id: find listing ids via PriceSnapshot -> ScrapeRun
    if search_id is not None:
        run_result = await db.execute(
            select(ScrapeRun.id).where(ScrapeRun.search_id == search_id)
        )
        run_ids = [r for (r,) in run_result.all()]
        if not run_ids:
            return PaginatedListings(items=[], total=0, page=page, page_size=page_size)
        snap_result = await db.execute(
            select(PriceSnapshot.listing_id)
            .where(PriceSnapshot.scrape_run_id.in_(run_ids))
            .distinct()
        )
        listing_ids = [r for (r,) in snap_result.all()]
        if not listing_ids:
            return PaginatedListings(items=[], total=0, page=page, page_size=page_size)
        stmt = stmt.where(Listing.id.in_(listing_ids))

    if source_id is not None:
        stmt = stmt.where(Listing.source_id == source_id)

    if status is not None:
        stmt = stmt.where(Listing.status == status)

    if min_price is not None:
        stmt = stmt.where(Listing.current_price_thb >= min_price)

    if max_price is not None:
        stmt = stmt.where(Listing.current_price_thb <= max_price)

    if condition is not None:
        stmt = stmt.where(Listing.condition == condition)

    if location is not None:
        stmt = stmt.where(Listing.location.ilike(f"%{location}%"))

    # Sorting — always append .id as tiebreaker to guarantee deterministic pagination
    if sort == "price_asc":
        stmt = stmt.order_by(Listing.current_price_thb.asc(), Listing.id.asc())
    elif sort == "price_desc":
        stmt = stmt.order_by(Listing.current_price_thb.desc(), Listing.id.asc())
    elif sort == "oldest":
        stmt = stmt.order_by(Listing.first_seen_at.asc(), Listing.id.asc())
    else:  # newest
        stmt = stmt.order_by(Listing.first_seen_at.desc(), Listing.id.asc())

    # Count total
    from sqlalchemy import func, select as sa_select
    count_stmt = sa_select(func.count()).select_from(stmt.subquery())
    total_result = await db.execute(count_stmt)
    total = total_result.scalar_one()

    # Pagination
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(stmt)
    listings = result.scalars().all()

    return PaginatedListings(
        items=[_to_response(l) for l in listings],
        total=total,
        page=page,
        page_size=page_size,
    )


class PriceStatsResponse(BaseModel):
    listing_id: int
    snapshots_count: int
    period_days: int
    price_current: float
    price_min: Optional[float]
    price_max: Optional[float]
    price_avg: Optional[float]
    trend_7d: Optional[Literal["up", "down", "stable"]]
    trend_7d_pct: Optional[float]
    is_likely_fake_sale: bool
    fake_sale_reason: Optional[str]


@router.get("/{listing_id}/price-stats", response_model=PriceStatsResponse)
async def get_price_stats(listing_id: int, db: AsyncSession = Depends(get_db)):
    listing = await db.get(Listing, listing_id)
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")

    period_days = 30
    cutoff = datetime.now(timezone.utc) - timedelta(days=period_days)
    stmt = (
        select(PriceSnapshot)
        .where(PriceSnapshot.listing_id == listing_id)
        .where(PriceSnapshot.scraped_at >= cutoff)
        .order_by(PriceSnapshot.scraped_at.asc())
    )
    result = await db.execute(stmt)
    snapshots = result.scalars().all()

    price_current = float(listing.current_price_thb)
    snapshots_count = len(snapshots)

    if snapshots_count == 0:
        return PriceStatsResponse(
            listing_id=listing_id,
            snapshots_count=0,
            period_days=period_days,
            price_current=price_current,
            price_min=None,
            price_max=None,
            price_avg=None,
            trend_7d=None,
            trend_7d_pct=None,
            is_likely_fake_sale=False,
            fake_sale_reason=None,
        )

    prices = [float(s.price_thb) for s in snapshots]
    price_min = min(prices)
    price_max = max(prices)
    price_avg = sum(prices) / snapshots_count

    # Trend 7d: oldest snapshot within last 7 days
    cutoff_7d = datetime.now(timezone.utc) - timedelta(days=7)
    snapshots_7d = [s for s in snapshots if s.scraped_at >= cutoff_7d]
    oldest_7d_price = float(snapshots_7d[0].price_thb) if snapshots_7d else 0.0
    if snapshots_7d and oldest_7d_price != 0:
        trend_7d_pct = ((price_current - oldest_7d_price) / oldest_7d_price) * 100
        if trend_7d_pct < -2:
            trend_7d = "down"
        elif trend_7d_pct > 2:
            trend_7d = "up"
        else:
            trend_7d = "stable"
    else:
        trend_7d = None
        trend_7d_pct = None

    # Flash sale detection (only when snapshots_count >= 3)
    if snapshots_count >= 3 and price_max > price_avg * 1.20 and price_current < price_avg * 0.90:
        is_likely_fake_sale = True
        fake_sale_reason = f"Price peaked at ฿{price_max:,.0f} before this apparent discount"
    else:
        is_likely_fake_sale = False
        fake_sale_reason = None

    log.info("price_stats_computed", listing_id=listing_id, snapshots_count=snapshots_count, trend_7d=trend_7d)

    return PriceStatsResponse(
        listing_id=listing_id,
        snapshots_count=snapshots_count,
        period_days=period_days,
        price_current=price_current,
        price_min=price_min,
        price_max=price_max,
        price_avg=round(price_avg, 2),
        trend_7d=trend_7d,
        trend_7d_pct=round(trend_7d_pct, 2) if trend_7d_pct is not None else None,
        is_likely_fake_sale=is_likely_fake_sale,
        fake_sale_reason=fake_sale_reason,
    )


@router.get("/{listing_id}/price-history")
async def get_price_history(
    listing_id: int,
    range: str = Query(default="30d", pattern="^(7d|30d|90d|all)$"),
    db: AsyncSession = Depends(get_db),
):
    listing = await db.get(Listing, listing_id)
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")

    stmt = select(PriceSnapshot).where(PriceSnapshot.listing_id == listing_id)

    if range != "all":
        days = {"7d": 7, "30d": 30, "90d": 90}[range]
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        stmt = stmt.where(PriceSnapshot.scraped_at >= cutoff)

    stmt = stmt.order_by(PriceSnapshot.scraped_at.asc())
    result = await db.execute(stmt)
    snapshots = result.scalars().all()

    return [
        {"ts": snap.scraped_at.isoformat(), "price": float(snap.price_thb)}
        for snap in snapshots
    ]


@router.get("/{listing_id}", response_model=ListingResponse)
async def get_listing(listing_id: int, db: AsyncSession = Depends(get_db)):
    listing = await db.get(Listing, listing_id)
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")
    return _to_response(listing)


@router.get("/{listing_id}/seller", response_model=SellerRisk)
async def get_seller_info(listing_id: int, db: AsyncSession = Depends(get_db)):
    """Return seller signals and risk classification for a listing.

    Uses the seller_payload stored in the listing row (written by scrape_task).
    No additional scraping is performed — this is pure data analysis.
    """
    listing = await db.get(Listing, listing_id)
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")

    signals = extract_seller_signals(listing.seller_payload or {})
    risk = classify_seller_risk(signals)

    log.info("seller_info_fetched", listing_id=listing_id, warning_level=risk.warning_level)
    return risk
