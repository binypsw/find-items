"""Watchlist beat task — runs every 30 minutes.

For each SavedSearch with ``watchlist_mode=True``:
1. Dispatch ``run_search`` (reuses the existing scrape pipeline).
2. Wait ~90 seconds for results to land in the DB.
3. Query listings that appeared after ``last_watchlist_run_at``.
4. Send a Discord embed if new listings were found.
5. Update ``last_watchlist_run_at`` to now.

Design notes
------------
- Uses the same ``run_search`` task as manual runs — no duplicate scrape logic.
- Browser-headed scrapers (Shopee, Lazada in headed mode) will fail silently in
  this automated context because there is no display available.  This is an
  accepted limitation: those sources simply return 0 items for watchlist runs.
- The 90-second sleep is intentional — scraping can take 30–60 s per source
  and we need results in the DB before querying new listings.
- ``last_watchlist_run_at`` is set to *before* the scrape dispatch so that any
  listing inserted during the scrape window is captured in the query.
"""
import asyncio
import time
from datetime import datetime, timezone

import structlog

from worker.celery_app import celery_app

log = structlog.get_logger()

# Seconds to wait after dispatching scrape tasks before querying new listings.
_SCRAPE_WAIT_SECONDS = 90


@celery_app.task(name="worker.tasks.watchlist_task.run_watchlist_checks")
def run_watchlist_checks() -> dict:
    """Orchestrator: fan-out watchlist checks for all active watchlist searches."""
    return asyncio.run(_run_watchlist_checks_async())


async def _run_watchlist_checks_async() -> dict:
    from sqlalchemy import select
    from shared.models.search import SavedSearch
    from worker.db import worker_session

    async with worker_session() as db:
        result = await db.execute(
            select(SavedSearch).where(
                SavedSearch.watchlist_mode == True,  # noqa: E712
                SavedSearch.is_active == True,       # noqa: E712
            )
        )
        searches = result.scalars().all()

    if not searches:
        log.debug("watchlist.no_active_searches")
        return {"status": "ok", "checked": 0}

    log.info("watchlist.dispatch", count=len(searches))

    dispatched = 0
    for search in searches:
        try:
            check_watchlist_search.apply_async(args=[search.id])
            dispatched += 1
        except Exception as exc:
            log.warning("watchlist.dispatch_failed", search_id=search.id, error=str(exc))

    return {"status": "ok", "dispatched": dispatched}


@celery_app.task(
    bind=True,
    max_retries=2,
    default_retry_delay=120,
    name="worker.tasks.watchlist_task.check_watchlist_search",
)
def check_watchlist_search(self, search_id: int) -> dict:
    """Run scrape for one watchlist search, then notify if new listings appeared."""
    return asyncio.run(_check_watchlist_search_async(self, search_id))


async def _check_watchlist_search_async(task, search_id: int) -> dict:
    from sqlalchemy import select
    from shared.models.listing import Listing, ListingStatus
    from shared.models.search import SavedSearch
    from shared.models.app_config import AppConfig
    from shared.services.notifications import notify_watchlist_new_items
    from worker.db import worker_session
    from worker.tasks.scrape_task import run_search

    now = datetime.now(timezone.utc)

    # Fetch search and record the cutoff timestamp BEFORE we dispatch the scrape,
    # so listings inserted during the scrape window are captured.
    async with worker_session() as db:
        search = await db.get(SavedSearch, search_id)
        if not search or not search.watchlist_mode or not search.is_active:
            return {"status": "skipped", "search_id": search_id}

        # The "new since" cutoff: last watchlist run, or search creation time as fallback.
        cutoff = search.last_watchlist_run_at or search.created_at
        search_name = search.name
        raw_query = search.raw_query

        # Mark last_watchlist_run_at immediately so the next cycle doesn't re-notify
        # for items found in this run.
        search.last_watchlist_run_at = now
        search.updated_at = now
        await db.commit()

    log.info("watchlist.scrape_start", search_id=search_id, cutoff=cutoff.isoformat())

    # Dispatch the scrape (same pipeline as manual run).
    try:
        run_search.apply_async(
            args=[search_id],
            kwargs={"triggered_by": "schedule"},
        )
    except Exception as exc:
        log.warning("watchlist.scrape_dispatch_failed", search_id=search_id, error=str(exc))
        raise task.retry(exc=exc)

    # Wait for scrape results to land.
    log.info("watchlist.waiting", search_id=search_id, seconds=_SCRAPE_WAIT_SECONDS)
    await asyncio.sleep(_SCRAPE_WAIT_SECONDS)

    # Query listings first seen after the cutoff that belong to a scrape_run for this search.
    # We join via PriceSnapshot (which carries scrape_run_id) to scope results to this search.
    async with worker_session() as db:
        from shared.models.price_snapshot import PriceSnapshot
        from shared.models.scrape_run import ScrapeRun

        result = await db.execute(
            select(
                Listing.id,
                Listing.title,
                Listing.current_price_thb,
                Listing.url,
                Listing.source_id,
                Listing.first_seen_at,
            )
            .join(PriceSnapshot, PriceSnapshot.listing_id == Listing.id)
            .join(ScrapeRun, ScrapeRun.id == PriceSnapshot.scrape_run_id)
            .where(
                ScrapeRun.search_id == search_id,
                Listing.first_seen_at >= cutoff,
                Listing.status == ListingStatus.ACTIVE,
            )
            .distinct(Listing.id)
            .order_by(Listing.id, Listing.current_price_thb)
            .limit(50)
        )
        rows = result.all()

        # Fetch optional webhook override
        webhook_row = await db.get(AppConfig, "discord_webhook_url")
        webhook_url: str | None = webhook_row.value if webhook_row else None

    new_listings = [
        {
            "id": row[0],
            "title": row[1],
            "price": float(row[2]),
            "url": row[3],
            "source_id": row[4],
            "first_seen_at": row[5].isoformat() if row[5] else None,
        }
        for row in rows
    ]

    log.info(
        "watchlist.new_listings",
        search_id=search_id,
        count=len(new_listings),
    )

    if new_listings:
        try:
            await notify_watchlist_new_items(
                search_name=search_name,
                search_id=search_id,
                new_listings=new_listings,
                webhook_url=webhook_url,
            )
        except Exception as exc:
            log.warning(
                "watchlist.notify_failed",
                search_id=search_id,
                error=str(exc),
            )

    return {
        "status": "ok",
        "search_id": search_id,
        "new_listings": len(new_listings),
    }
