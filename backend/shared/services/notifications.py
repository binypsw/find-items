"""Discord notification service.

Sends rich embeds to a Discord webhook URL.  All functions are async;
fire-and-forget callers should ``asyncio.create_task`` them or use the
Celery ``send_notification`` task.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional

import httpx
import structlog

from shared.config import get_settings

log = structlog.get_logger()

# Discord embed colours (decimal)
_COLOR_WARNING = 0xFFA500   # orange
_COLOR_SUCCESS = 0x2ECC71   # green
_COLOR_INFO = 0x3498DB      # blue
_COLOR_ERROR = 0xE74C3C     # red


async def send_discord(
    message: str,
    webhook_url: Optional[str] = None,
    *,
    embeds: Optional[list[dict]] = None,
) -> bool:
    """Send a plain message (and optional embeds) to a Discord webhook.

    Returns ``True`` on success, ``False`` on failure (never raises).
    """
    settings = get_settings()
    url = webhook_url or settings.discord_webhook_url
    if not url:
        log.debug("notifications.discord_skipped", reason="no webhook url configured")
        return False

    payload: dict[str, Any] = {"content": message}
    if embeds:
        payload["embeds"] = embeds

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(
                url,
                content=json.dumps(payload),
                headers={"Content-Type": "application/json"},
            )
            if r.status_code in (200, 204):
                log.debug("notifications.discord_sent", status=r.status_code)
                return True
            else:
                log.warning(
                    "notifications.discord_failed",
                    status=r.status_code,
                    body=r.text[:200],
                )
                return False
    except Exception as exc:
        log.warning("notifications.discord_error", error=str(exc))
        return False


async def notify_quota_warning(
    source_id: str,
    credits_used: int,
    budget: int,
    pct: float,
    webhook_url: Optional[str] = None,
) -> bool:
    """Send a quota-warning embed.

    Example embed:
        "WARNING shopee quota 82% (147600/180000 credits)"
    """
    embed = {
        "title": f"WARNING {source_id} quota at {pct:.0%}",
        "description": (
            f"**{credits_used:,}** of **{budget:,}** credits used this month "
            f"({pct:.1%})"
        ),
        "color": _COLOR_WARNING,
        "footer": {"text": "Find-Item scraper"},
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "fields": [
            {"name": "Source", "value": source_id, "inline": True},
            {"name": "Credits used", "value": str(credits_used), "inline": True},
            {"name": "Monthly budget", "value": str(budget), "inline": True},
        ],
    }
    return await send_discord("", webhook_url=webhook_url, embeds=[embed])


async def notify_price_drop(
    listing_id: int,
    title: str,
    url: str,
    old_price: float,
    new_price: float,
    drop_pct: float,
    source_id: str,
    webhook_url: Optional[str] = None,
) -> bool:
    """Send a price-drop embed when a listing's price falls >= 5%.

    Example embed title: "💸 Price Drop — iPhone 14 Pro 128GB (used)…"
    """
    embed = {
        "title": f"\U0001f4b8 Price Drop — {title[:60]}",
        "url": url,
        "color": _COLOR_SUCCESS,
        "footer": {"text": "Find-Item price tracker"},
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "fields": [
            {"name": "Source", "value": source_id, "inline": True},
            {"name": "Old Price", "value": f"฿{old_price:,.2f}", "inline": True},
            {"name": "New Price", "value": f"฿{new_price:,.2f}", "inline": True},
            {"name": "Drop %", "value": f"{drop_pct:.1f}%", "inline": True},
        ],
    }
    return await send_discord("", webhook_url=webhook_url, embeds=[embed])


async def notify_watchlist_new_items(
    search_name: str,
    search_id: int,
    new_listings: list[dict],
    webhook_url: Optional[str] = None,
) -> bool:
    """Send a watchlist-new-items embed when auto-scrape finds fresh listings.

    ``new_listings`` is a list of dicts with keys: title, price, url, source_id.
    Sends at most 5 items in the embed to stay within Discord's field limit.
    """
    if not new_listings:
        return False

    top = new_listings[:5]
    fields: list[dict] = []
    for item in top:
        fields.append({
            "name": item.get("title", "")[:80],
            "value": (
                f"฿{item.get('price', 0):,.0f} — [{item.get('source_id', '')}]"
                f"({item.get('url', '')})"
            ),
            "inline": False,
        })

    more = len(new_listings) - len(top)
    footer_text = (
        f"Find-Item watchlist | +{more} more" if more > 0 else "Find-Item watchlist"
    )

    embed = {
        "title": f"\U0001f514 New Listings — {search_name[:60]}",
        "color": _COLOR_INFO,
        "footer": {"text": footer_text},
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "fields": fields,
    }
    return await send_discord("", webhook_url=webhook_url, embeds=[embed])


async def notify_daily_summary(
    stats: dict,
    webhook_url: Optional[str] = None,
) -> bool:
    """Send a daily summary embed.

    ``stats`` is expected to have keys like::

        {
            "date": "2026-05-02",
            "searches_run": 12,
            "items_found": 340,
            "sources": {
                "shopee": {"runs": 4, "items": 120, "credits": 500},
                ...
            },
        }
    """
    date_str = stats.get("date", datetime.now(timezone.utc).date().isoformat())
    searches = stats.get("searches_run", 0)
    items = stats.get("items_found", 0)

    fields: list[dict] = [
        {"name": "Searches run", "value": str(searches), "inline": True},
        {"name": "Items found", "value": str(items), "inline": True},
    ]

    sources: dict = stats.get("sources", {})
    for sid, s_stats in sources.items():
        fields.append({
            "name": sid,
            "value": (
                f"runs={s_stats.get('runs', 0)} "
                f"items={s_stats.get('items', 0)} "
                f"credits={s_stats.get('credits', 0)}"
            ),
            "inline": True,
        })

    embed = {
        "title": f"Daily Summary — {date_str}",
        "color": _COLOR_INFO,
        "footer": {"text": "Find-Item scraper"},
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "fields": fields,
    }
    return await send_discord("", webhook_url=webhook_url, embeds=[embed])
