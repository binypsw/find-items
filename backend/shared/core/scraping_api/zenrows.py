from typing import Any, Literal, Optional

import httpx
import structlog

from shared.config import get_settings

log = structlog.get_logger()

CreditTier = Literal["basic", "js_render", "premium"]

_TIER_PARAMS: dict[CreditTier, dict[str, Any]] = {
    "basic":     {"js_render": "false", "premium_proxy": "false"},
    "js_render": {"js_render": "true",  "premium_proxy": "false"},
    "premium":   {"js_render": "true",  "premium_proxy": "true", "antibot": "true"},
}


class ZenRowsClient:
    """Thin wrapper around ZenRows API with adaptive credit tiering.

    Lazy premium: try basic (1 credit) → js_render (5 credits) → premium (~25 credits).
    Expected savings: avg 4-6 credits/req vs 25 for full premium every time.
    """

    BASE_URL = "https://api.zenrows.com/v1/"

    def __init__(self, api_key: str | None = None):
        settings = get_settings()
        self._api_key = api_key or settings.zenrows_api_key or ""

    def _is_blocked(self, response: httpx.Response) -> bool:
        if response.status_code in (403, 429, 503):
            return True
        # ZenRows returns 400 with code REQS002 when the target site requires
        # JS rendering or premium proxies — treat as "needs escalation"
        if response.status_code == 400:
            body = response.text[:400]
            if "REQS002" in body or "js_render" in body or "premium_proxy" in body:
                return True
        text = response.text[:200].lower()
        return any(kw in text for kw in ("access denied", "captcha", "blocked", "bot detected"))

    async def get(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        adaptive: bool = True,
        timeout: int = 30,
    ) -> httpx.Response:
        """Fetch URL via ZenRows.

        With adaptive=True (default), escalates tier only if blocked.
        With adaptive=False, uses basic tier directly.
        """
        tiers: list[CreditTier] = (["basic", "js_render", "premium"] if adaptive else ["basic"])

        async with httpx.AsyncClient(timeout=timeout) as client:
            for tier in tiers:
                req_params = {
                    "apikey": self._api_key,
                    "url": url,
                    **(params or {}),
                    **_TIER_PARAMS[tier],
                }
                log.debug("zenrows.request", url=url, tier=tier)
                r = await client.get(self.BASE_URL, params=req_params)

                if not self._is_blocked(r):
                    log.info("zenrows.success", url=url, tier=tier, status=r.status_code)
                    return r

                log.warning("zenrows.blocked", url=url, tier=tier, status=r.status_code)

        return r  # return last response even if all tiers failed
