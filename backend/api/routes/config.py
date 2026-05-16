from datetime import datetime, timezone
from typing import Optional

import structlog
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from shared.config import get_settings
from shared.database import get_db
from shared.models.app_config import AppConfig

log = structlog.get_logger()
router = APIRouter(prefix="/api/config", tags=["config"])

DISCORD_WEBHOOK_KEY = "discord_webhook_url"


class NotificationConfigResponse(BaseModel):
    discord_webhook_url: Optional[str]


class NotificationConfigRequest(BaseModel):
    discord_webhook_url: Optional[str]


@router.get("/notifications", response_model=NotificationConfigResponse)
async def get_notification_config(
    db: AsyncSession = Depends(get_db),
) -> NotificationConfigResponse:
    row = await db.get(AppConfig, DISCORD_WEBHOOK_KEY)
    if row:
        return NotificationConfigResponse(discord_webhook_url=row.value or None)

    # Fallback to env var
    settings = get_settings()
    return NotificationConfigResponse(discord_webhook_url=settings.discord_webhook_url)


@router.put("/notifications", response_model=NotificationConfigResponse)
async def put_notification_config(
    body: NotificationConfigRequest,
    db: AsyncSession = Depends(get_db),
) -> NotificationConfigResponse:
    url = body.discord_webhook_url

    if not url:
        # Delete the row if it exists
        row = await db.get(AppConfig, DISCORD_WEBHOOK_KEY)
        if row:
            await db.delete(row)
            await db.commit()
            log.info("config.discord_webhook_deleted")
        return NotificationConfigResponse(discord_webhook_url=None)

    # Upsert
    row = await db.get(AppConfig, DISCORD_WEBHOOK_KEY)
    if row:
        row.value = url
        row.updated_at = datetime.now(timezone.utc)
    else:
        row = AppConfig(
            key=DISCORD_WEBHOOK_KEY,
            value=url,
            updated_at=datetime.now(timezone.utc),
        )
        db.add(row)

    await db.commit()
    log.info("config.discord_webhook_updated")
    return NotificationConfigResponse(discord_webhook_url=url)
