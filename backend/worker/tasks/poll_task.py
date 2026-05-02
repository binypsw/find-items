"""Per-listing polling task.

The Celery beat job ``poll-due-listings`` runs every 5 minutes and
queries for all listings whose ``next_poll_at`` is in the past.  For
each due listing it enqueues a lightweight ``refresh_listing`` sub-task
that re-scrapes that single item's detail page and updates the DB.

Design notes
------------
- ``next_poll_at`` is set by ``scrape_task.scrape_source`` after each
  run: ``now + poll_interval_minutes``.
- Default ``poll_interval_minutes`` = 720 (12 h) — configurable per
  listing in the DB.
- ``refresh_listing`` re-uses the scraper's ``get_detail`` method.
  If the scraper returns ``None`` (e.g. Lazada, which doesn't support
  detail pages yet) the listing's ``consecutive_missing_count`` is
  incremented.  At 5+ consecutive misses the status is flipped to
  ``stale``.
"""
import asyncio
from datetime import datetime, timedelta, timezone

import structlog
from celery import group

from worker.celery_app import celery_app

log = structlog.get_logger()

_MISSING_STALE_THRESHOLD = 5  # consecutive misses → mark listing stale


@celery_app.task(name="worker.tasks.poll_task.dispatch_due_polls")
def dispatch_due_polls() -> dict:
    """Orchestrator: find due listings and fan-out refresh sub-tasks."""
    return asyncio.run(_dispatch_due_polls_async())


async def _dispatch_due_polls_async() -> dict:
    from sqlalchemy import select
    from shared.models.listing import Listing, ListingStatus
    from worker.db import worker_session

    now = datetime.now(timezone.utc)

    async with worker_session() as db:
        result = await db.execute(
            select(Listing.id, Listing.source_id, Listing.url)
            .where(
                Listing.next_poll_at <= now,
                Listing.status == ListingStatus.ACTIVE,
            )
            .order_by(Listing.next_poll_at)
            .limit(500)  # cap to avoid fan-out explosion
        )
        rows = result.all()

    if not rows:
        log.debug("dispatch_due_polls.none_due")
        return {"status": "ok", "dispatched": 0}

    tasks = group(
        refresh_listing.s(listing_id, source_id, url)
        for listing_id, source_id, url in rows
    )
    tasks.apply_async()
    log.info("dispatch_due_polls.dispatched", count=len(rows))
    return {"status": "ok", "dispatched": len(rows)}


@celery_app.task(
    bind=True,
    max_retries=3,
    retry_backoff=True,
    name="worker.tasks.poll_task.refresh_listing",
)
def refresh_listing(self, listing_id: int, source_id: str, url: str) -> dict:
    """Re-scrape a single listing's detail page and update the DB."""
    return asyncio.run(_refresh_listing_async(self, listing_id, source_id, url))


async def _refresh_listing_async(
    task, listing_id: int, source_id: str, url: str
) -> dict:
    import hashlib
    import json
    from decimal import Decimal

    from shared.models.listing import Listing, ListingStatus
    from shared.models.price_snapshot import PriceSnapshot
    from shared.scraper.manager import get_scraper
    from worker.db import worker_session

    now = datetime.now(timezone.utc)

    async with worker_session() as db:
        listing = await db.get(Listing, listing_id)
        if not listing or listing.status != ListingStatus.ACTIVE:
            return {"status": "skipped", "listing_id": listing_id}

        scraper = get_scraper(source_id, db)
        if not scraper:
            return {"status": "no_scraper", "listing_id": listing_id}

        try:
            raw = await scraper.get_detail(url)
        except Exception as exc:
            log.warning("refresh_listing.error", listing_id=listing_id, error=str(exc))
            raise task.retry(exc=exc)

        # Advance next_poll_at regardless of outcome
        listing.next_poll_at = now + timedelta(minutes=listing.poll_interval_minutes)

        if raw is None:
            # Detail page not available (scraper doesn't support it yet)
            listing.consecutive_missing_count = (listing.consecutive_missing_count or 0) + 1
            if listing.consecutive_missing_count >= _MISSING_STALE_THRESHOLD:
                listing.status = ListingStatus.STALE
                log.info(
                    "refresh_listing.stale",
                    listing_id=listing_id,
                    misses=listing.consecutive_missing_count,
                )
            await db.commit()
            return {"status": "no_detail", "listing_id": listing_id}

        # Reset missing counter
        listing.consecutive_missing_count = 0

        # Detect price change
        new_price = raw.price
        old_price = listing.current_price_thb
        price_changed = abs(new_price - old_price) > Decimal("0.01")

        if price_changed:
            listing.current_price_thb = new_price
            listing.price_change_count = (listing.price_change_count or 0) + 1
            log.info(
                "refresh_listing.price_change",
                listing_id=listing_id,
                old=float(old_price),
                new=float(new_price),
            )
            if new_price < old_price:
                drop_pct = float((old_price - new_price) / old_price * 100)
                if drop_pct >= 5.0:
                    try:
                        from shared.services.notifications import notify_price_drop
                        await notify_price_drop(
                            listing_id=listing_id,
                            title=raw.title,
                            url=str(raw.url),
                            old_price=float(old_price),
                            new_price=float(new_price),
                            drop_pct=drop_pct,
                            source_id=source_id,
                        )
                    except Exception as _e:
                        log.warning("refresh_listing.notify_price_drop_failed", error=str(_e))

        listing.last_seen_at = now
        listing.title = raw.title or listing.title
        listing.last_payload_hash = hashlib.sha256(
            json.dumps(raw.raw_payload, sort_keys=True, default=str).encode()
        ).hexdigest()[:64]

        # Always insert a price snapshot so we can chart history
        snapshot = PriceSnapshot(
            listing_id=listing_id,
            price_thb=new_price,
            price_original=raw.price,
            currency=raw.currency.value,
            scraped_at=now,
            scrape_run_id=None,  # not associated with a bulk run
        )
        db.add(snapshot)

        await db.commit()

    return {
        "status": "refreshed",
        "listing_id": listing_id,
        "price_changed": price_changed,
    }
