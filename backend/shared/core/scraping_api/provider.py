"""Provider abstraction layer for scraping APIs.

Defines a Protocol so scrapers can be typed against a stable interface,
and provides ``best_provider_fetch`` which tries ZenRows first then
falls back to Scrapfly.
"""
from typing import Protocol, runtime_checkable

import structlog

from shared.config import get_settings

log = structlog.get_logger()


@runtime_checkable
class ScrapingProvider(Protocol):
    """Minimal interface that every scraping API client must satisfy."""

    async def fetch(self, url: str, *, render_js: bool = False) -> tuple[str, int]:
        """Fetch *url* and return ``(html, credits_used)``."""
        ...


class _ZenRowsProviderAdapter:
    """Wraps ZenRowsClient so it satisfies ScrapingProvider."""

    def __init__(self):
        from shared.core.scraping_api.zenrows import ZenRowsClient
        self._client = ZenRowsClient()

    async def fetch(self, url: str, *, render_js: bool = False) -> tuple[str, int]:
        r = await self._client.get(url, adaptive=True)
        # ZenRows credit cost: basic=1, js_render=5, premium~25
        # We can't know the exact tier used from the response; use a conservative estimate.
        credits_used = 5 if render_js else 1
        return r.text, credits_used


class _ScrapflyProviderAdapter:
    """Wraps ScrapflyApiClient so it satisfies ScrapingProvider."""

    def __init__(self):
        from shared.core.scraping_api.scrapfly import ScrapflyApiClient
        self._client = ScrapflyApiClient()

    async def fetch(self, url: str, *, render_js: bool = False) -> tuple[str, int]:
        return await self._client.get(url, render_js=render_js, asp=True)


def _build_providers() -> list[ScrapingProvider]:
    """Build the ordered provider list based on available API keys."""
    settings = get_settings()
    providers: list[ScrapingProvider] = []
    if settings.zenrows_api_key:
        providers.append(_ZenRowsProviderAdapter())
    if settings.scrapfly_api_key:
        providers.append(_ScrapflyProviderAdapter())
    return providers


async def best_provider_fetch(url: str, *, render_js: bool = False) -> tuple[str, int]:
    """Try available scraping providers in priority order.

    Priority: ZenRows (adaptive tiering) → Scrapfly (ASP bypass).

    Returns the first successful ``(html, credits_used)`` tuple.
    Raises ``RuntimeError`` if all providers fail or none are configured.
    """
    providers = _build_providers()
    if not providers:
        raise RuntimeError(
            "No scraping API provider configured. "
            "Set ZENROWS_API_KEY or SCRAPFLY_API_KEY in .env."
        )

    last_exc: Exception | None = None
    for provider in providers:
        try:
            html, credits = await provider.fetch(url, render_js=render_js)
            log.info(
                "provider.success",
                url=url,
                provider=type(provider).__name__,
                credits=credits,
            )
            return html, credits
        except Exception as exc:
            log.warning(
                "provider.failed",
                url=url,
                provider=type(provider).__name__,
                error=str(exc),
            )
            last_exc = exc

    raise RuntimeError(
        f"All scraping providers failed for {url!r}"
    ) from last_exc
