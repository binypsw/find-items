from decimal import Decimal
from typing import Optional

import structlog
import redis.asyncio as aioredis

from shared.config import get_settings

log = structlog.get_logger()

_FX_KEY_PREFIX = "finditem:fx:"
_FX_TTL = 86400  # 24h


class CurrencyConverter:
    """Convert foreign currencies to THB using daily FX rates stored in Redis.

    Rates are fetched by the beat task update_fx_rates (00:30 daily).
    Falls back to hardcoded defaults if Redis has no rate yet.
    """

    _FALLBACK_RATES: dict[str, float] = {
        "USD": 35.0,
        "CNY": 4.8,
        "JPY": 0.24,
        "EUR": 38.0,
        "GBP": 44.0,
    }

    def __init__(self, redis_url: str | None = None):
        settings = get_settings()
        self._url = redis_url or settings.redis_url
        self._client: Optional[aioredis.Redis] = None

    async def _get_client(self) -> aioredis.Redis:
        if self._client is None:
            self._client = aioredis.from_url(self._url, decode_responses=True)
        return self._client

    async def get_rate(self, currency: str) -> float:
        """Return THB per 1 unit of currency."""
        if currency == "THB":
            return 1.0
        try:
            client = await self._get_client()
            raw = await client.get(f"{_FX_KEY_PREFIX}{currency}")
            if raw:
                return float(raw)
        except Exception as e:
            log.warning("currency.redis_fail", error=str(e), currency=currency)
        return self._FALLBACK_RATES.get(currency, 1.0)

    async def to_thb(self, amount: Decimal, currency: str) -> Decimal:
        if currency == "THB":
            return amount
        rate = await self.get_rate(currency)
        return (amount * Decimal(str(rate))).quantize(Decimal("0.01"))

    async def store_rate(self, currency: str, rate: float) -> None:
        client = await self._get_client()
        await client.setex(f"{_FX_KEY_PREFIX}{currency}", _FX_TTL, str(rate))
        log.info("currency.rate_stored", currency=currency, rate=rate)
