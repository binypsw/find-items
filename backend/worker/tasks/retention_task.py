"""Data retention task — runs daily at 03:00 Bangkok time.

Retention policy
----------------
price_snapshots
  < 30 days       keep all
  30–90 days      keep 1 per day per listing  (downsample)
  90–365 days     keep 1 per week per listing (downsample)
  > 365 days      hard delete

listings
  status IN (stale, deleted) AND last_seen_at < 90 days ago → hard delete

The downsampling approach:
  For each (listing_id, day/week bucket) keep the row with the MAX id
  (i.e. the last snapshot in that bucket) and delete the rest.
  This preserves the most recent reading per period without losing
  long-run price trend data.
"""
import asyncio
from datetime import datetime, timedelta, timezone

import structlog
from worker.celery_app import celery_app

log = structlog.get_logger()


@celery_app.task(name="worker.tasks.retention_task.run_retention")
def run_retention() -> dict:
    """Data retention policy — runs daily at 03:00 BKK."""
    return asyncio.run(_run_retention_async())


async def _run_retention_async() -> dict:
    from sqlalchemy import text
    from worker.db import worker_session

    now = datetime.now(timezone.utc)
    stats: dict = {}

    async with worker_session() as db:
        # ---------------------------------------------------------------- #
        # 1. Downsample: keep 1 per day for snapshots 30–90 days old
        # ---------------------------------------------------------------- #
        cutoff_30d = now - timedelta(days=30)
        cutoff_90d = now - timedelta(days=90)

        result = await db.execute(text("""
            DELETE FROM price_snapshots
            WHERE id IN (
                SELECT id FROM price_snapshots
                WHERE scraped_at >= :start AND scraped_at < :end
                  AND id NOT IN (
                      SELECT MAX(id)
                      FROM price_snapshots
                      WHERE scraped_at >= :start AND scraped_at < :end
                      GROUP BY listing_id,
                               DATE_TRUNC('day', scraped_at AT TIME ZONE 'UTC')
                  )
            )
        """), {"start": cutoff_90d, "end": cutoff_30d})
        stats["downsampled_daily"] = result.rowcount

        # ---------------------------------------------------------------- #
        # 2. Downsample: keep 1 per week for snapshots 90–365 days old
        # ---------------------------------------------------------------- #
        cutoff_365d = now - timedelta(days=365)

        result = await db.execute(text("""
            DELETE FROM price_snapshots
            WHERE id IN (
                SELECT id FROM price_snapshots
                WHERE scraped_at >= :start AND scraped_at < :end
                  AND id NOT IN (
                      SELECT MAX(id)
                      FROM price_snapshots
                      WHERE scraped_at >= :start AND scraped_at < :end
                      GROUP BY listing_id,
                               DATE_TRUNC('week', scraped_at AT TIME ZONE 'UTC')
                  )
            )
        """), {"start": cutoff_365d, "end": cutoff_90d})
        stats["downsampled_weekly"] = result.rowcount

        # ---------------------------------------------------------------- #
        # 3. Hard-delete snapshots older than 1 year
        # ---------------------------------------------------------------- #
        result = await db.execute(text("""
            DELETE FROM price_snapshots
            WHERE scraped_at < :cutoff
        """), {"cutoff": cutoff_365d})
        stats["deleted_old_snapshots"] = result.rowcount

        # ---------------------------------------------------------------- #
        # 4. Hard-delete stale/deleted listings older than 90 days
        # ---------------------------------------------------------------- #
        result = await db.execute(text("""
            DELETE FROM listings
            WHERE status IN ('stale', 'deleted')
              AND last_seen_at < :cutoff
        """), {"cutoff": cutoff_90d})
        stats["deleted_old_listings"] = result.rowcount

        await db.commit()

    log.info("run_retention.done", **stats)
    return {"status": "ok", **stats}
