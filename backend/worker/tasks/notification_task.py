import asyncio
from datetime import datetime, timedelta, timezone

import structlog

from worker.celery_app import celery_app

log = structlog.get_logger()


@celery_app.task(name="worker.tasks.notification_task.send_daily_summary")
def send_daily_summary() -> dict:
    """Aggregate yesterday's scrape stats and send a Discord summary embed.

    Runs daily at 08:00 Bangkok time (UTC+7).  Queries the DB for all
    ScrapeRun rows finished in the previous calendar day and builds a
    per-source breakdown to pass to ``notify_daily_summary``.
    """
    return asyncio.run(_send_daily_summary_async())


async def _send_daily_summary_async() -> dict:
    from sqlalchemy import func, select
    from shared.models.scrape_run import ScrapeRun, ScrapeRunStatus
    from shared.services.notifications import notify_daily_summary
    from worker.db import worker_session

    # "Yesterday" in Bangkok time (UTC+7) → UTC range
    now_utc = datetime.now(timezone.utc)
    # Shift to Bangkok to find the correct calendar day
    bangkok_offset = timedelta(hours=7)
    today_bkk = (now_utc + bangkok_offset).date()
    yesterday_bkk = today_bkk - timedelta(days=1)

    # Convert back to UTC for DB queries
    from datetime import timezone as _tz
    import datetime as _dt
    day_start_utc = datetime(
        yesterday_bkk.year, yesterday_bkk.month, yesterday_bkk.day,
        0, 0, 0, tzinfo=timezone.utc
    ) - bangkok_offset
    day_end_utc = day_start_utc + timedelta(days=1)

    async with worker_session() as db:
        result = await db.execute(
            select(
                ScrapeRun.source_id,
                func.count(ScrapeRun.id).label("runs"),
                func.coalesce(func.sum(ScrapeRun.items_found), 0).label("items"),
                func.coalesce(func.sum(ScrapeRun.api_credits_used), 0).label("credits"),
            )
            .where(
                ScrapeRun.finished_at >= day_start_utc,
                ScrapeRun.finished_at < day_end_utc,
                ScrapeRun.status == ScrapeRunStatus.COMPLETED,
            )
            .group_by(ScrapeRun.source_id)
        )
        rows = result.all()

    sources: dict = {}
    total_items = 0
    total_runs = 0
    for row in rows:
        sources[row.source_id] = {
            "runs": row.runs,
            "items": int(row.items),
            "credits": int(row.credits),
        }
        total_items += int(row.items)
        total_runs += row.runs

    stats = {
        "date": str(yesterday_bkk),
        "searches_run": total_runs,
        "items_found": total_items,
        "sources": sources,
    }

    ok = await notify_daily_summary(stats)
    log.info("send_daily_summary.done", date=str(yesterday_bkk), sent=ok)
    return {"status": "ok" if ok else "discord_failed", "stats": stats}


@celery_app.task(name="worker.tasks.notification_task.send_notification")
def send_notification(notification_type: str, payload: dict, channels: list[str]) -> dict:
    """Send notification to specified channels (discord, websocket).

    ``notification_type`` — e.g. "quota_warning", "daily_summary", "item_found"
    ``payload``           — type-specific dict passed to the handler
    ``channels``          — list of "discord" | "websocket"
    """
    return asyncio.run(_send_notification_async(notification_type, payload, channels))


async def _send_notification_async(
    notification_type: str,
    payload: dict,
    channels: list[str],
) -> dict:
    from shared.services.notifications import (
        notify_daily_summary,
        notify_quota_warning,
        send_discord,
    )

    results: dict[str, bool] = {}

    if "discord" in channels:
        try:
            if notification_type == "quota_warning":
                ok = await notify_quota_warning(
                    source_id=payload.get("source_id", "unknown"),
                    credits_used=payload.get("credits_used", 0),
                    budget=payload.get("budget", 0),
                    pct=payload.get("pct", 0.0),
                    webhook_url=payload.get("webhook_url"),
                )
            elif notification_type == "daily_summary":
                ok = await notify_daily_summary(
                    stats=payload,
                    webhook_url=payload.get("webhook_url"),
                )
            else:
                # Generic plain-text Discord message
                message = payload.get("message") or f"[{notification_type}] {payload}"
                ok = await send_discord(
                    message,
                    webhook_url=payload.get("webhook_url"),
                )
            results["discord"] = ok
        except Exception as exc:
            log.warning("send_notification.discord_error", error=str(exc))
            results["discord"] = False

    if "websocket" in channels:
        # Websocket notifications are handled by the RedisPubSub layer directly;
        # this task only bridges external channels.
        log.info("send_notification.websocket_not_implemented")
        results["websocket"] = False

    log.info(
        "send_notification.done",
        type=notification_type,
        channels=channels,
        results=results,
    )
    return {"status": "ok", "results": results}
