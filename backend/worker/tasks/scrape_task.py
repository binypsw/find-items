import asyncio
import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal

import structlog
from celery import group
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from worker.celery_app import celery_app

log = structlog.get_logger()


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60, name="worker.tasks.scrape_task.run_search")
def run_search(
    self,
    search_id: int,
    source_filter: list[str] | None = None,
    triggered_by: Literal["manual", "schedule"] = "schedule",
) -> dict:
    """Orchestrate scraping for a saved search.

    Acquires a Redis lock to prevent duplicate concurrent runs.
    Spawns scrape_source sub-tasks as a Celery group.
    """
    return asyncio.run(_run_search_async(self, search_id, source_filter, triggered_by))


async def _run_search_async(task, search_id: int, source_filter, triggered_by):
    import redis.asyncio as aioredis
    from shared.config import get_settings
    from shared.models.search import SavedSearch
    from shared.models.scrape_run import ScrapeRun, ScrapeRunStatus
    from shared.models.source import Source
    from worker.db import worker_session

    settings = get_settings()
    redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    lock_key = f"lock:scrape:search:{search_id}"
    lock = redis.lock(lock_key, timeout=600)

    acquired = await lock.acquire(blocking=False)
    if not acquired:
        log.info("run_search.already_running", search_id=search_id)
        return {"status": "already_running", "search_id": search_id}

    try:
        async with worker_session() as db:
            search = await db.get(SavedSearch, search_id)
            if not search or not search.is_active:
                return {"status": "search_not_found", "search_id": search_id}

            # Determine which sources to run
            result = await db.execute(select(Source).where(Source.enabled == True))
            sources = result.scalars().all()
            source_ids = [s.id for s in sources if not source_filter or s.id in source_filter]

            if not source_ids:
                return {"status": "no_sources", "search_id": search_id}

            # Create scrape_run records for each source
            now = datetime.now(timezone.utc)
            run_ids = {}
            for sid in source_ids:
                run = ScrapeRun(
                    search_id=search_id,
                    source_id=sid,
                    started_at=now,
                    status=ScrapeRunStatus.PENDING,
                )
                db.add(run)
                await db.flush()
                run_ids[sid] = run.id

            await db.commit()

        # Dispatch sub-tasks
        tasks = group(
            scrape_source.s(search_id, sid, run_ids[sid])
            for sid in source_ids
        )
        result = tasks.apply_async()
        log.info("run_search.dispatched", search_id=search_id, sources=source_ids)
        return {"status": "dispatched", "search_id": search_id, "run_ids": run_ids}

    finally:
        await lock.release()
        await redis.aclose()


@celery_app.task(
    bind=True,
    max_retries=5,
    retry_backoff=True,
    retry_jitter=True,
    name="worker.tasks.scrape_task.scrape_source",
)
def scrape_source(self, search_id: int, source_id: str, run_id: int) -> dict:
    """Scrape a single source and upsert results into DB."""
    return asyncio.run(_scrape_source_async(self, search_id, source_id, run_id))


async def _scrape_source_async(task, search_id: int, source_id: str, run_id: int) -> dict:
    from shared.models.listing import Listing, ListingStatus
    from shared.models.price_snapshot import PriceSnapshot
    from shared.models.scrape_run import ScrapeRun, ScrapeRunStatus
    from shared.models.search import SavedSearch
    from shared.scraper.manager import get_scraper
    from shared.scraper.types import StructuredQuery
    from shared.core.pubsub import RedisPubSub
    from worker.db import worker_session

    pubsub = RedisPubSub()
    now = datetime.now(timezone.utc)

    async with worker_session() as db:
        # Update run status to running
        run = await db.get(ScrapeRun, run_id)
        if run:
            run.status = ScrapeRunStatus.RUNNING
            run.started_at = now
            await db.commit()

        # Load search query
        search = await db.get(SavedSearch, search_id)
        if not search:
            return {"status": "search_not_found"}

        parsed = search.parsed_query or {}
        if isinstance(parsed, str):
            parsed = json.loads(parsed)
        query = StructuredQuery(
            raw_query=search.raw_query,  # always pass original query for normalize_keywords
            keywords=parsed.get("keywords") or [search.raw_query],
            keywords_th=parsed.get("keywords_th", []),
            keywords_en=parsed.get("keywords_en", []),
            category=parsed.get("category"),
            max_price_thb=Decimal(str(parsed["max_price_thb"])) if parsed.get("max_price_thb") else None,
            min_price_thb=Decimal(str(parsed["min_price_thb"])) if parsed.get("min_price_thb") else None,
            location=parsed.get("location"),
        )

        scraper = get_scraper(source_id, db)
        if not scraper:
            # Mark run as FAILED — don't leave it stuck in RUNNING
            run = await db.get(ScrapeRun, run_id)
            if run:
                run.status = ScrapeRunStatus.FAILED
                run.errors = {"error": f"No scraper plugin for source '{source_id}' — not yet implemented"}
                run.finished_at = datetime.now(timezone.utc)
                await db.commit()
            log.warning("scrape_source.plugin_not_found", source_id=source_id)
            return {"status": "plugin_not_found", "source_id": source_id}

        items_found = items_new = items_updated = 0
        errors = []

        try:
            async for raw in scraper.search(query, limit=50):
                # Hash-and-skip: skip if payload unchanged
                payload_hash = hashlib.sha256(
                    json.dumps(raw.raw_payload, sort_keys=True, default=str).encode()
                ).hexdigest()[:64]

                # Default poll interval: 12 h (720 min)
                from datetime import timedelta
                _poll_minutes = 720
                _next_poll = now + timedelta(minutes=_poll_minutes)

                # Upsert listing
                stmt = pg_insert(Listing).values(
                    source_id=raw.source_id,
                    external_id=raw.external_id,
                    url=str(raw.url),
                    title=raw.title,
                    description=raw.description,
                    current_price_thb=raw.price,
                    price_original=raw.price,
                    currency=raw.currency.value,
                    condition=raw.condition.value,
                    seller_payload=raw.seller.model_dump(),
                    location=raw.location,
                    image_urls=[str(u) for u in raw.image_urls],
                    raw_payload=raw.raw_payload,
                    status=ListingStatus.ACTIVE.value,
                    first_seen_at=now,
                    last_seen_at=now,
                    last_payload_hash=payload_hash,
                    spec_tokens=[],
                    next_poll_at=_next_poll,
                    poll_interval_minutes=_poll_minutes,
                ).on_conflict_do_update(
                    constraint="uq_listing_source_external",
                    set_={
                        "title": raw.title,
                        "current_price_thb": raw.price,
                        "last_seen_at": now,
                        "status": ListingStatus.ACTIVE.value,
                        "last_payload_hash": payload_hash,
                        "consecutive_missing_count": 0,
                        "next_poll_at": _next_poll,
                        # Keep existing image if new scrape returns none (source temporarily has no image)
                        "image_urls": text(
                            "CASE WHEN jsonb_array_length(EXCLUDED.image_urls) > 0"
                            " THEN EXCLUDED.image_urls ELSE listings.image_urls END"
                        ),
                    },
                ).returning(Listing.id, Listing.price_change_count)

                result = await db.execute(stmt)
                row = result.fetchone()
                listing_id = row[0]
                items_found += 1

                # Insert price snapshot
                snapshot = PriceSnapshot(
                    listing_id=listing_id,
                    price_thb=raw.price,
                    price_original=raw.price,
                    currency=raw.currency.value,
                    scraped_at=now,
                    scrape_run_id=run_id,
                )
                db.add(snapshot)
                items_new += 1

                # Publish live event
                await pubsub.publish(run_id, {
                    "type": "item_found",
                    "run_id": run_id,
                    "search_id": search_id,
                    "source_id": source_id,
                    "payload": {"title": raw.title, "price": float(raw.price), "url": str(raw.url)},
                })

            await db.commit()

            # --- Credit tracking & quota warnings ---
            credits_used = getattr(scraper, "_credits_used", 0)

            # Update run as completed
            run = await db.get(ScrapeRun, run_id)
            if run:
                run.status = ScrapeRunStatus.COMPLETED
                run.finished_at = datetime.now(timezone.utc)
                run.items_found = items_found
                run.items_new = items_new
                run.items_updated = items_updated
                run.api_credits_used = credits_used

            # Accumulate credits on the Source row and check quota
            from shared.models.source import Source
            source_row = await db.get(Source, source_id)
            if source_row:
                source_row.last_success_at = datetime.now(timezone.utc)
                source_row.health_status = "healthy"
            if source_row and credits_used > 0:
                prev_used = source_row.credits_used_this_month or 0
                new_used = prev_used + credits_used
                source_row.credits_used_this_month = new_used

                budget = source_row.monthly_credit_budget or 0
                if budget > 0:
                    prev_pct = prev_used / budget
                    new_pct = new_used / budget
                    # Fire once per threshold crossing (70 / 90 / 100 %)
                    thresholds = [0.70, 0.90, 1.00]
                    for threshold in thresholds:
                        if prev_pct < threshold <= new_pct:
                            try:
                                from shared.services.notifications import notify_quota_warning
                                await notify_quota_warning(
                                    source_id=source_id,
                                    credits_used=new_used,
                                    budget=budget,
                                    pct=new_pct,
                                )
                            except Exception as _notif_exc:
                                log.warning(
                                    "scrape_source.quota_notify_failed",
                                    error=str(_notif_exc),
                                )
                            break  # only one notification per run

            await db.commit()

        except Exception as e:
            log.error("scrape_source.error", source_id=source_id, error=str(e))
            errors.append(str(e))
            run = await db.get(ScrapeRun, run_id)
            if run:
                run.status = ScrapeRunStatus.FAILED
                run.errors = {"error": str(e)}
                run.finished_at = datetime.now(timezone.utc)
                await db.commit()

            await pubsub.publish(run_id, {
                "type": "error",
                "run_id": run_id,
                "search_id": search_id,
                "source_id": source_id,
                "payload": {"error": str(e)},
            })
            raise task.retry(exc=e)

        finally:
            await pubsub.publish(run_id, {
                "type": "completed",
                "run_id": run_id,
                "search_id": search_id,
                "source_id": source_id,
                "payload": {"items_found": items_found},
            })
            await pubsub.close()

    return {
        "status": "completed",
        "source_id": source_id,
        "items_found": items_found,
        "items_new": items_new,
        "errors": errors,
    }


@celery_app.task(name="worker.tasks.scrape_task.update_source_health")
def update_source_health() -> dict:
    return asyncio.run(_update_source_health_async())


async def _update_source_health_async() -> dict:
    from datetime import timedelta
    from sqlalchemy import select
    from shared.models.source import Source
    from worker.db import worker_session

    now = datetime.now(timezone.utc)
    updated = 0

    async with worker_session() as db:
        result = await db.execute(select(Source).where(Source.enabled == True))
        sources = result.scalars().all()

        for source in sources:
            if source.last_success_at is None:
                status = "down"
            else:
                age = now - source.last_success_at
                if age < timedelta(hours=24):
                    status = "healthy"
                elif age < timedelta(hours=72):
                    status = "degraded"
                else:
                    status = "down"

            if source.health_status != status:
                source.health_status = status
                updated += 1

        await db.commit()

    log.info("update_source_health.done", updated=updated)
    return {"status": "ok", "updated": updated}


@celery_app.task(name="worker.tasks.scrape_task.update_fx_rates")
def update_fx_rates() -> dict:
    return asyncio.run(_update_fx_rates_async())


async def _update_fx_rates_async() -> dict:
    from shared.core.currency import CurrencyConverter

    converter = CurrencyConverter()
    try:
        from forex_python.converter import CurrencyRates
        cr = CurrencyRates()
        for currency in ["USD", "CNY", "JPY", "EUR", "GBP"]:
            rate = cr.get_rate(currency, "THB")
            await converter.store_rate(currency, rate)
        log.info("update_fx_rates.done")
        return {"status": "ok"}
    except Exception as e:
        log.warning("update_fx_rates.failed", error=str(e))
        return {"status": "error", "error": str(e)}


@celery_app.task(name="worker.tasks.scrape_task.recluster_orphan_products")
def recluster_orphan_products() -> dict:
    log.info("recluster_orphan_products.start")
    return asyncio.run(_recluster_orphan_products_async())


async def _recluster_orphan_products_async() -> dict:
    from sqlalchemy import select, text
    from shared.models.listing import Listing, ListingStatus
    from shared.models.product import Product
    from shared.core.embeddings import embed_text
    from worker.db import worker_session

    processed = 0
    matched = 0
    created = 0

    async with worker_session() as db:
        # 1. Fetch orphan listings (no product_id, active, limit 200)
        result = await db.execute(
            select(Listing)
            .where(Listing.product_id.is_(None), Listing.status == ListingStatus.ACTIVE)
            .limit(200)
        )
        listings = result.scalars().all()

        batch_updates: list[tuple[Listing, int]] = []  # (listing, product_id)

        for listing in listings:
            try:
                embedding = embed_text(listing.title)
            except Exception as exc:
                log.warning(
                    "recluster.embed_failed",
                    listing_id=listing.id,
                    error=str(exc),
                )
                continue

            # 3. Find nearest product via pgvector cosine distance
            try:
                nn_result = await db.execute(
                    text(
                        "SELECT id FROM products "
                        "WHERE embedding <=> :emb < 0.25 "
                        "ORDER BY embedding <=> :emb "
                        "LIMIT 1"
                    ),
                    {"emb": str(embedding)},
                )
                row = nn_result.fetchone()
            except Exception as exc:
                log.warning(
                    "recluster.vector_query_failed",
                    listing_id=listing.id,
                    error=str(exc),
                )
                continue

            if row:
                # 4. Matched an existing product
                product_id = row[0]
                listing.product_id = product_id
                matched += 1
            else:
                # 5. Create a new product
                new_product = Product(
                    canonical_title=listing.title,
                    embedding=embedding,
                    first_seen_at=datetime.now(timezone.utc),
                )
                db.add(new_product)
                await db.flush()  # get new_product.id
                listing.product_id = new_product.id
                created += 1

            processed += 1

            # 6. Commit in batches of 50
            if processed % 50 == 0:
                await db.commit()

        # Final commit for remaining rows
        if processed % 50 != 0:
            await db.commit()

    log.info(
        "recluster_orphan_products.done",
        processed=processed,
        matched=matched,
        created=created,
    )
    return {"status": "ok", "processed": processed, "matched": matched, "created": created}
