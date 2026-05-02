"""Scrapfly API client with ASP (anti-scraping protection) bypass.

Uses scrapfly-sdk (sync) wrapped in a thread executor so callers can
await it like any other async client.
"""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

import structlog

from shared.config import get_settings

log = structlog.get_logger()

_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="scrapfly")

# Credit cost lookup — approximate, helps callers track quota
_CREDIT_COSTS = {
    (False, False): 1,    # basic
    (True, False): 5,     # js render only
    (False, True): 10,    # asp only
    (True, True): 25,     # asp + js render (premium)
}


class ScrapflyApiClient:
    """Thin async wrapper around scrapfly-sdk.

    scrapfly-sdk is synchronous; we run it in a ThreadPoolExecutor so
    callers can ``await client.get(url)``.

    Returns ``(html_text, credits_used)`` so callers can track quota.
    """

    def __init__(self, api_key: Optional[str] = None):
        settings = get_settings()
        self._api_key = api_key or settings.scrapfly_api_key or ""

    def _sync_fetch(self, url: str, render_js: bool, asp: bool, timeout: int) -> tuple[str, int]:
        """Blocking fetch — called from a thread pool."""
        from scrapfly import ScrapflyClient, ScrapeConfig  # type: ignore

        with ScrapflyClient(key=self._api_key, max_concurrency=1) as client:
            config = ScrapeConfig(
                url=url,
                asp=asp,
                render_js=render_js,
                country="TH",
            )
            result = client.scrape(config)
            credits_used = _CREDIT_COSTS.get((render_js, asp), 10)
            # Prefer the reported cost from the API if available
            if hasattr(result, "context") and result.context:
                api_cost = result.context.get("cost")
                if api_cost is not None:
                    try:
                        credits_used = int(api_cost)
                    except (TypeError, ValueError):
                        pass
            return result.scrape_result["content"], credits_used

    async def get(
        self,
        url: str,
        *,
        render_js: bool = False,
        asp: bool = True,
        timeout: int = 30,
    ) -> tuple[str, int]:
        """Fetch *url* via Scrapfly.

        Parameters
        ----------
        url:
            Target URL to scrape.
        render_js:
            Execute JavaScript in a headless browser (~5-10 extra credits).
        asp:
            Enable anti-scraping protection bypass (recommended for Shopee/Lazada).
        timeout:
            Request timeout in seconds.

        Returns
        -------
        (html_text, credits_used)
        """
        loop = asyncio.get_event_loop()
        log.debug("scrapfly.request", url=url, render_js=render_js, asp=asp)
        try:
            html, credits = await loop.run_in_executor(
                _executor,
                lambda: self._sync_fetch(url, render_js, asp, timeout),
            )
            log.info("scrapfly.success", url=url, credits=credits)
            return html, credits
        except Exception as exc:
            log.warning("scrapfly.error", url=url, error=str(exc))
            raise
