from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse

import structlog
from fastapi import APIRouter, Depends
from pydantic import BaseModel, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from shared.config import get_settings
from shared.database import get_db
from shared.models.app_config import AppConfig

log = structlog.get_logger()
router = APIRouter(prefix="/api/config", tags=["config"])

DISCORD_WEBHOOK_KEY = "discord_webhook_url"

_ALLOWED_WEBHOOK_HOSTS = {
    "discord.com",
    "discordapp.com",
    "ptb.discord.com",
    "canary.discord.com",
}


class NotificationConfigResponse(BaseModel):
    discord_webhook_url: Optional[str]


class NotificationConfigRequest(BaseModel):
    discord_webhook_url: Optional[str]

    @field_validator("discord_webhook_url")
    @classmethod
    def validate_discord_url(cls, v: Optional[str]) -> Optional[str]:
        if not v:
            return v
        parsed = urlparse(v)
        if parsed.scheme != "https":
            raise ValueError("Webhook URL must use HTTPS")
        if (parsed.hostname or "") not in _ALLOWED_WEBHOOK_HOSTS:
            raise ValueError(
                "Webhook host must be a Discord domain "
                f"({', '.join(sorted(_ALLOWED_WEBHOOK_HOSTS))})"
            )
        return v


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
