from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

import structlog
from playwright.async_api import BrowserContext, async_playwright

from shared.config import get_settings

log = structlog.get_logger()


class BrowserlessClient:
    """Playwright client that connects to a remote browserless/chrome service via CDP WebSocket.

    The worker container does NOT install Chromium — it connects to the browserless service.
    """

    def __init__(self, url: str | None = None, token: str | None = None):
        settings = get_settings()
        self._url = url or settings.browserless_url
        self._token = token or settings.browserless_token

    @property
    def ws_endpoint(self) -> str:
        return f"{self._url}?token={self._token}"

    @asynccontextmanager
    async def context(
        self,
        cookies: list[dict] | None = None,
        extra_http_headers: dict | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[BrowserContext]:
        """Yield a Playwright BrowserContext connected to browserless.

        Cookies are injected into the context before yielding, enabling
        authenticated scraping (e.g. Facebook Marketplace with stored session).
        """
        async with async_playwright() as p:
            browser = await p.chromium.connect_over_cdp(self.ws_endpoint)
            try:
                ctx = await browser.new_context(
                    extra_http_headers=extra_http_headers or {},
                    **kwargs,
                )
                if cookies:
                    await ctx.add_cookies(cookies)
                log.info("browserless.context_opened", url=self._url)
                try:
                    yield ctx
                finally:
                    await ctx.close()
                    log.info("browserless.context_closed")
            finally:
                await browser.close()
