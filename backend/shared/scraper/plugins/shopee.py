"""Shopee Thailand scraper.

Uses Camoufox (anti-detect Firefox) to navigate the Shopee search page,
then intercepts the internal JSON search API response.

Anti-bot strategy:
- Camoufox patches Firefox at the binary level to pass Akamai Bot Manager
  fingerprint checks (JA3/JA4 TLS, navigator properties, canvas, WebGL, etc.)
- Route interception captures the search result JSON.

Credit cost: 0 (local Firefox via Camoufox, no paid service).
"""
import asyncio
import json as jsonlib
import urllib.parse
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import AsyncIterator

import structlog
from camoufox.async_api import AsyncCamoufox

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
        tier="browserless",
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

        # Load stored cookies (SPC_F, SPC_EC, SPC_U, etc.) if available.
        # User must POST to /api/sessions with source_id="shopee" to seed them.
        stored_cookies: list[dict] | None = None
        if self.deps.cookie_store:
            try:
                stored_cookies = await self.deps.cookie_store.get_active("shopee")
            except Exception as exc:
                log.debug("shopee.cookie_load_error", error=str(exc))

        # Residential proxy support (BrightData format: http://user:pass@host:port).
        # If SHOPEE_PROXY_URL is not set, proxy_kwargs stays None and is omitted.
        proxy_kwargs: dict | None = None
        proxy_url = get_settings().shopee_proxy_url
        if proxy_url:
            parsed = urllib.parse.urlparse(proxy_url)
            proxy_kwargs = {
                "server": f"{parsed.scheme}://{parsed.hostname}:{parsed.port}",
                "username": parsed.username,
                "password": parsed.password,
            }
            log.debug("shopee.proxy_enabled", server=proxy_kwargs["server"])

        captured_data: dict | None = None

        launch_kwargs: dict = dict(
            headless=True,
            os="windows",
            locale=["th-TH", "en-US"],
        )
        if proxy_kwargs:
            launch_kwargs["proxy"] = proxy_kwargs

        try:
            async with AsyncCamoufox(**launch_kwargs) as browser:
                # Use new_page() so fingerprint patches from Camoufox apply to
                # the auto-created default context. new_context() would bypass them.
                page = await browser.new_page()
                ctx = page.context

                async def _intercept_api(route):
                    nonlocal captured_data
                    try:
                        response = await route.fetch()
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
                        await route.fulfill(response=response)
                    except Exception as exc:
                        log.debug("shopee.route_error", error=str(exc))
                        try:
                            await route.continue_()
                        except Exception:
                            pass

                if stored_cookies:
                    try:
                        await ctx.add_cookies(stored_cookies)
                        log.info("shopee.cookies_injected", count=len(stored_cookies), keyword=keyword)
                    except Exception as exc:
                        log.warning("shopee.cookie_inject_error", error=str(exc))
                        stored_cookies = None

                warmup_sleep = 2 if stored_cookies else 4
                try:
                    await page.goto(
                        "https://shopee.co.th/",
                        wait_until="commit",
                        timeout=30_000,
                    )
                    await asyncio.sleep(warmup_sleep)
                except Exception as exc:
                    log.debug("shopee.warmup_timeout", error=str(exc))

                await page.route(
                    lambda url: _SEARCH_API_PATTERN in url,
                    _intercept_api,
                )

                try:
                    await page.goto(
                        search_url,
                        wait_until="commit",
                        timeout=30_000,
                    )
                    await asyncio.sleep(8)
                except Exception as exc:
                    log.debug("shopee.goto_timeout", error=str(exc))

        except Exception as exc:
            log.warning("shopee.camoufox_error", error=str(exc), keyword=keyword)
            return

        if not captured_data or captured_data.get("error"):
            error_code = captured_data.get("error") if captured_data else None
            if error_code == 90309999:
                log.warning(
                    "shopee.bot_blocked",
                    keyword=keyword,
                    has_cookies=bool(stored_cookies),
                    hint="Akamai Bot Manager — redirects to verify/traffic/error. Needs Scrapfly or anti-detect browser.",
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
