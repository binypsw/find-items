"""Shopee Thailand scraper.

Uses Playwright with a **persistent browser context** (Chromium, headed) to navigate
the Shopee search page, then captures the internal JSON search API response via a
response event listener.

Anti-bot strategy
-----------------
Akamai Bot Manager (error 90309999) blocks headless/automated browsers.
Running headed (headless=False) with a persistent context lets the user manually
solve the Akamai challenge once — cookies and browser state are saved to disk so
subsequent runs reuse the valid session without prompting again.

First-run flow
--------------
1. Chromium opens visibly (headless=False).
2. User solves the Akamai / CAPTCHA challenge in the browser window.
3. Session state is written automatically to ``user_data_dir``.
4. Future runs load the saved context; the challenge is typically not repeated.

Persistent context path (inside Docker volume, configurable via env var):
    SHOPEE_CONTEXT_PATH=/data/browser-contexts/shopee  (default)

DB tier update (run once after deploy):
    UPDATE sources SET tier='browser_headed' WHERE id='shopee';
"""
import asyncio
import json as jsonlib
import urllib.parse
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import AsyncIterator

import structlog
from playwright.async_api import async_playwright

from shared.config import get_settings
from shared.scraper.base import AbstractScraper, ScraperConfig
from shared.scraper.types import Condition, Currency, RawListing, SellerInfo, StructuredQuery

log = structlog.get_logger()

IMAGE_BASE = "https://cf.shopee.co.th/file/"

_SEARCH_API_PATTERN = "api/v4/search/search_items"

_SEARCH_PAGE = "https://shopee.co.th/search?keyword={keyword}"


class ShopeeScraper(AbstractScraper):
    source_id = "shopee"
    display_name = "Shopee Thailand"
    base_url = "https://shopee.co.th"
    config = ScraperConfig(
        tier="browser_headed",
        rate_limit_rps=0.3,
        api_provider=None,
    )

    def __init__(self, deps):
        super().__init__(deps)
        self._credits_used: int = 0  # no paid API credits

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def search(self, query: StructuredQuery, limit: int = 50) -> AsyncIterator[RawListing]:
        keyword = self.normalize_keywords(query)
        encoded_kw = urllib.parse.quote(keyword)
        search_url = _SEARCH_PAGE.format(keyword=encoded_kw)

        settings = get_settings()
        context_path = settings.shopee_context_path

        # Proxy support (BrightData format: http://user:pass@host:port).
        # Omitted when SHOPEE_PROXY_URL is not set.
        proxy_kwargs: dict | None = None
        proxy_url = settings.shopee_proxy_url
        if proxy_url:
            parsed = urllib.parse.urlparse(proxy_url)
            proxy_kwargs = {
                "server": f"{parsed.scheme}://{parsed.hostname}:{parsed.port}",
                "username": parsed.username,
                "password": parsed.password,
            }
            log.debug("shopee.proxy_enabled", server=proxy_kwargs["server"])

        captured_data: dict | None = None

        # launch_persistent_context kwargs — proxy added only when configured
        launch_kwargs: dict = dict(
            headless=False,
            locale="th-TH",
            viewport={"width": 1280, "height": 900},
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
            ],
        )
        if proxy_kwargs:
            launch_kwargs["proxy"] = proxy_kwargs

        log.info(
            "shopee.browser_start",
            keyword=keyword,
            context_path=context_path,
        )

        try:
            async with async_playwright() as pw:
                # launch_persistent_context saves cookies/storage to disk automatically.
                # First run: user solves Akamai challenge; subsequent runs reuse session.
                context = await pw.chromium.launch_persistent_context(
                    user_data_dir=context_path,
                    **launch_kwargs,
                )
                try:
                    page = await context.new_page()

                    # Response listener captures the search API JSON.
                    async def _on_response(response) -> None:
                        nonlocal captured_data
                        if _SEARCH_API_PATTERN not in response.url:
                            return
                        try:
                            body_bytes = await response.body()
                            if body_bytes:
                                captured_data = jsonlib.loads(body_bytes)
                                items_count = len(
                                    (captured_data.get("response") or {}).get("items") or []
                                )
                                log.debug(
                                    "shopee.api_captured",
                                    items=items_count,
                                    error_code=captured_data.get("error"),
                                )
                        except Exception as exc:
                            log.debug("shopee.response_read_error", error=str(exc))

                    page.on("response", _on_response)

                    # Warmup: visit homepage first so session cookies are active before search.
                    try:
                        await page.goto(
                            "https://shopee.co.th/",
                            wait_until="commit",
                            timeout=30_000,
                        )
                        await asyncio.sleep(3)
                    except Exception as exc:
                        log.debug("shopee.warmup_timeout", error=str(exc))

                    # Navigate to search results page.
                    try:
                        await page.goto(
                            search_url,
                            wait_until="commit",
                            timeout=30_000,
                        )
                        # Wait for the search API XHR to fire and listener to capture it.
                        await asyncio.sleep(8)
                    except Exception as exc:
                        log.debug("shopee.goto_timeout", error=str(exc))

                finally:
                    await context.close()

        except Exception as exc:
            log.warning("shopee.browser_error", error=str(exc), keyword=keyword)
            return

        if not captured_data or captured_data.get("error"):
            error_code = captured_data.get("error") if captured_data else None
            if error_code == 90309999:
                log.warning(
                    "shopee.bot_blocked",
                    keyword=keyword,
                    hint=(
                        "Akamai blocked — open the browser window that just appeared, "
                        "solve the challenge manually, then retry. "
                        "Session will be saved to the persistent context path for future runs."
                    ),
                )
            else:
                log.warning("shopee.api_error", error_code=error_code, keyword=keyword)
            captured_data = None

        items = (captured_data.get("response") or {}).get("items") if captured_data else []
        if not items:
            log.info("shopee.no_items_from_api", keyword=keyword)
            return

        yielded = 0
        for raw_item in items:
            if yielded >= limit:
                return
            listing = self._normalize(raw_item)
            if listing:
                yield listing
                yielded += 1

    async def get_detail(self, url: str) -> RawListing | None:
        """Shopee detail pages require JS; not implemented."""
        return None

    # ------------------------------------------------------------------
    # Normalization
    # ------------------------------------------------------------------

    def _normalize(self, raw_item: dict) -> RawListing | None:
        try:
            # API wraps each product in item_basic (or itemBasic)
            ib: dict = (
                raw_item.get("item_basic")
                or raw_item.get("itemBasic")
                or raw_item
            )
            if not ib:
                return None

            ext_id = str(ib.get("itemid") or ib.get("id") or "")
            if not ext_id:
                return None

            shopid = str(ib.get("shopid") or "")
            product_url = f"https://shopee.co.th/product/{shopid}/{ext_id}"

            # Shopee stores price as integer × 100 000
            raw_price = ib.get("price") or ib.get("price_min") or 0
            try:
                price = Decimal(str(raw_price)) / Decimal("100000")
            except InvalidOperation:
                price = Decimal("0")

            title = ib.get("name") or ib.get("title") or ""
            location = ib.get("shop_location") or None

            cond_raw = ib.get("condition", 0)
            condition = (
                Condition.NEW if cond_raw == 1
                else Condition.USED if cond_raw == 2
                else Condition.UNKNOWN
            )

            # Images
            image_key = ib.get("image", "")
            raw_images = ib.get("images") or []
            if raw_images:
                image_urls = [
                    f"{IMAGE_BASE}{img}" if not str(img).startswith("http") else str(img)
                    for img in raw_images
                ]
            elif image_key:
                image_urls = [
                    f"{IMAGE_BASE}{image_key}"
                    if not str(image_key).startswith("http")
                    else str(image_key)
                ]
            else:
                image_urls = []

            sold = ib.get("sold") or ib.get("historical_sold") or 0
            seller = SellerInfo(
                name=None,
                sold_count=int(sold) if sold else None,
            )

            return RawListing(
                source_id=self.source_id,
                external_id=ext_id,
                url=product_url,
                title=title,
                description=None,
                price=price,
                currency=Currency.THB,
                condition=condition,
                seller=seller,
                location=location,
                image_urls=image_urls,
                posted_at=None,
                scraped_at=datetime.now(timezone.utc),
                raw_payload=raw_item,
            )
        except Exception as exc:
            log.debug("shopee.normalize_error", error=str(exc))
            return None
