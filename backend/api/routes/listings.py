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

    # Sorting
    if sort == "price_asc":
        stmt = stmt.order_by(Listing.current_price_thb.asc())
    elif sort == "price_desc":
        stmt = stmt.order_by(Listing.current_price_thb.desc())
    elif sort == "oldest":
        stmt = stmt.order_by(Listing.first_seen_at.asc())
    else:  # newest
        stmt = stmt.order_by(Listing.first_seen_at.desc())

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


@router.get("/{listing_id}", response_model=ListingResponse)
async def get_listing(listing_id: int, db: AsyncSession = Depends(get_db)):
    listing = await db.get(Listing, listing_id)
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")
    return _to_response(listing)


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
