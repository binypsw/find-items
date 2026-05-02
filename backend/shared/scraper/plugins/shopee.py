"""Shopee Thailand scraper.

Uses Scrapfly (render_js + ASP bypass) to render the search page, then
extracts product data from the embedded ``window.__INITIAL_STATE__`` JSON
injected by Shopee's React frontend.

Anti-bot notes:
- Shopee's internal JSON API requires ``SPC_F`` + ``af-ac-enc-dat`` auth tokens
  that can only be obtained from a live browser session — direct HTTP calls are
  blocked regardless of proxy tier.
- Rendering the full page and reading state from the DOM bypasses this because
  the real browser session authenticates transparently inside Scrapfly's sandbox.

Credit cost: ~25 credits/request (render_js + ASP).
"""
import asyncio
import json
import re
import urllib.parse
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import AsyncIterator

import structlog

from shared.scraper.base import AbstractScraper, ScraperConfig
from shared.scraper.types import Condition, Currency, RawListing, SellerInfo, StructuredQuery

log = structlog.get_logger()

IMAGE_BASE = "https://cf.shopee.co.th/file/"
_PAGE_SIZE = 30  # items Shopee renders per search page


class ShopeeScraper(AbstractScraper):
    source_id = "shopee"
    display_name = "Shopee Thailand"
    base_url = "https://shopee.co.th"
    config = ScraperConfig(
        tier="managed_api",
        rate_limit_rps=0.3,          # gentle — each request is expensive
        api_provider="scrapfly",
    )

    def __init__(self, deps):
        super().__init__(deps)
        self._credits_used: int = 0

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def search(self, query: StructuredQuery, limit: int = 50) -> AsyncIterator[RawListing]:
        from shared.core.scraping_api.scrapfly import ScrapflyApiClient

        keyword = self.normalize_keywords(query)
        yielded = 0
        page = 0  # Shopee uses 0-based page index in URL

        scrapfly = ScrapflyApiClient()

        while yielded < limit:
            url = (
                f"https://shopee.co.th/search"
                f"?keyword={urllib.parse.quote(keyword)}&page={page}"
            )

            try:
                html, credits = await scrapfly.get(url, render_js=True, asp=True)
                self._credits_used += credits
            except Exception as exc:
                log.warning("shopee.search_error", error=str(exc), page=page)
                break

            items = self._extract_items(html)
            if not items:
                log.info("shopee.no_items", page=page, keyword=keyword)
                break

            for raw_item in items:
                if yielded >= limit:
                    return
                listing = self._normalize(raw_item)
                if listing:
                    yield listing
                    yielded += 1

            if len(items) < _PAGE_SIZE:
                break  # last page

            page += 1
            await asyncio.sleep(1.0 / self.config.rate_limit_rps)

    async def get_detail(self, url: str) -> RawListing | None:
        """Shopee detail pages require JS; return None for now."""
        return None

    # ------------------------------------------------------------------
    # HTML extraction
    # ------------------------------------------------------------------

    def _extract_items(self, html: str) -> list[dict]:
        """Pull product items out of the rendered Shopee HTML.

        Tries three strategies in order:
        1. ``window.__INITIAL_STATE__`` script injection (most reliable)
        2. ``window.pageData`` variants used by some Shopee sub-domains
        3. JSON-LD structured data (fallback, rarely present on Shopee TH)
        """
        # Strategy 1: window.__INITIAL_STATE__
        items = self._try_initial_state(html)
        if items is not None:
            return items

        # Strategy 2: window.pageData
        items = self._try_page_data(html)
        if items is not None:
            return items

        # Strategy 3: embedded <script type="application/json">
        items = self._try_script_json(html)
        if items is not None:
            return items

        log.warning("shopee.extraction_failed", html_snippet=html[:300])
        return []

    def _try_initial_state(self, html: str) -> list[dict] | None:
        m = re.search(
            r'window\.__INITIAL_STATE__\s*=\s*(\{.+?\});\s*</script>',
            html,
            re.DOTALL,
        )
        if not m:
            return None
        try:
            state = json.loads(m.group(1))
        except (json.JSONDecodeError, ValueError):
            return None

        # Path: searchPageData → itemResult → item
        items = (
            state.get("searchPageData", {})
                 .get("itemResult", {})
                 .get("item", [])
        )
        if items:
            return items

        # Alternative path (some Shopee builds)
        items = state.get("searchResult", {}).get("items", [])
        if items:
            return items

        return None

    def _try_page_data(self, html: str) -> list[dict] | None:
        m = re.search(
            r'window\.pageData\s*=\s*(\{.+?\});\s*</script>',
            html,
            re.DOTALL,
        )
        if not m:
            return None
        try:
            data = json.loads(m.group(1))
            items = data.get("items") or data.get("data", {}).get("items", [])
            return items if items else None
        except (json.JSONDecodeError, ValueError):
            return None

    def _try_script_json(self, html: str) -> list[dict] | None:
        """Look for any <script type=application/json> that has an items array."""
        for blob in re.findall(
            r'<script[^>]+type=["\']application/json["\'][^>]*>(.+?)</script>',
            html,
            re.DOTALL,
        ):
            try:
                data = json.loads(blob)
                items = data.get("items") or data.get("data", {}).get("items", [])
                if items and isinstance(items, list):
                    return items
            except (json.JSONDecodeError, ValueError):
                continue
        return None

    # ------------------------------------------------------------------
    # Normalization
    # ------------------------------------------------------------------

    def _normalize(self, raw_item: dict) -> RawListing | None:
        try:
            # Search results wrap the item in "itemBasic" or "item_basic"
            ib: dict = (
                raw_item.get("itemBasic")
                or raw_item.get("item_basic")
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
