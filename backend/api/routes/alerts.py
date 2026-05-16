from datetime import datetime, timezone
from typing import Literal, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.database import get_db
from shared.models.listing import Listing
from shared.models.price_alert import PriceAlert

log = structlog.get_logger()
router = APIRouter(prefix="/api/alerts", tags=["alerts"])

VALID_COMPARISONS = {"lte", "pct_drop"}


class AlertResponse(BaseModel):
    id: int
    listing_id: int
    listing_title: str
    listing_url: str
    target_price: float
    comparison: str
    notify_channels: list[str]
    is_active: bool
    triggered_at: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True


class CreateAlertRequest(BaseModel):
    listing_id: int
    target_price: float
    comparison: str
    notify_channels: list[Literal["discord"]] = ["discord"]

    @field_validator("comparison")
    @classmethod
    def validate_comparison(cls, v: str) -> str:
        if v not in VALID_COMPARISONS:
            raise ValueError(f"comparison must be one of: {sorted(VALID_COMPARISONS)}")
        return v


class UpdateAlertRequest(BaseModel):
    target_price: Optional[float] = None
    is_active: Optional[bool] = None
    notify_channels: Optional[list[Literal["discord"]]] = None


async def _to_response(alert: PriceAlert, db: AsyncSession) -> AlertResponse:
    listing = await db.get(Listing, alert.listing_id)
    listing_title = listing.title if listing else ""
    listing_url = listing.url if listing else ""
    return AlertResponse(
        id=alert.id,
        listing_id=alert.listing_id,
        listing_title=listing_title,
        listing_url=listing_url,
        target_price=float(alert.target_price),
        comparison=alert.comparison,
        notify_channels=alert.notify_channels or [],
        is_active=alert.is_active,
        triggered_at=alert.triggered_at,
        created_at=alert.created_at,
    )


@router.get("", response_model=list[AlertResponse])
async def list_alerts(db: AsyncSession = Depends(get_db)) -> list[AlertResponse]:
    result = await db.execute(
        select(PriceAlert).order_by(PriceAlert.created_at.desc())
    )
    alerts = result.scalars().all()
    return [await _to_response(a, db) for a in alerts]


@router.post("", response_model=AlertResponse, status_code=201)
async def create_alert(
    body: CreateAlertRequest, db: AsyncSession = Depends(get_db)
) -> AlertResponse:
    listing = await db.get(Listing, body.listing_id)
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")

    alert = PriceAlert(
        listing_id=body.listing_id,
        target_price=body.target_price,
        comparison=body.comparison,
        notify_channels=body.notify_channels,
        is_active=True,
        triggered_at=None,
        created_at=datetime.now(timezone.utc),
    )
    db.add(alert)
    await db.commit()
    await db.refresh(alert)

    log.info(
        "alert.created",
        alert_id=alert.id,
        listing_id=alert.listing_id,
        comparison=alert.comparison,
        target_price=float(alert.target_price),
    )
    return await _to_response(alert, db)


@router.patch("/{alert_id}", response_model=AlertResponse)
async def update_alert(
    alert_id: int, body: UpdateAlertRequest, db: AsyncSession = Depends(get_db)
) -> AlertResponse:
    alert = await db.get(PriceAlert, alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    if body.target_price is not None:
        alert.target_price = body.target_price
    if body.is_active is not None:
        alert.is_active = body.is_active
    if body.notify_channels is not None:
        alert.notify_channels = body.notify_channels

    await db.commit()
    await db.refresh(alert)

    log.info("alert.updated", alert_id=alert_id)
    return await _to_response(alert, db)


@router.delete("/{alert_id}", status_code=204)
async def delete_alert(alert_id: int, db: AsyncSession = Depends(get_db)) -> None:
    alert = await db.get(PriceAlert, alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    await db.delete(alert)
    await db.commit()
    log.info("alert.deleted", alert_id=alert_id)
