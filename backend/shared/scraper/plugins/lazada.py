"""Lazada Thailand scraper.

Uses Browserless (Playwright) to navigate the Lazada catalog page with a real
Chromium browser, then intercepts the internal AJAX catalog API response.

Lazada's bot protection (/punish tmd) requires real JS execution to pass.
Browserless bypasses this by running a genuine Chrome session.

Credit cost: 0 (uses our own Browserless container, no paid proxy).
"""
import asyncio
import re
import urllib.parse
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import AsyncIterator

import structlog

from shared.scraper.base import AbstractScraper, ScraperConfig
from shared.scraper.types import Condition, Currency, RawListing, SellerInfo, StructuredQuery

log = structlog.get_logger()

_SEARCH_URL = "https://www.lazada.co.th/catalog/"
_AJAX_PATTERN = "catalog/?ajax=true"  # substring found in intercepted XHR URLs


class LazadaScraper(AbstractScraper):
    source_id = "lazada"
    display_name = "Lazada Thailand"
    base_url = "https://www.lazada.co.th"
    config = ScraperConfig(tier="browserless", rate_limit_rps=0.3)

    def __init__(self, deps):
        super().__init__(deps)
        self._credits_used: int = 0  # no paid API credits

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def search(self, query: StructuredQuery, limit: int = 50) -> AsyncIterator[RawListing]:
        keyword = self.normalize_keywords(query)
        encoded_kw = urllib.parse.quote(keyword)
        search_url = f"{_SEARCH_URL}?q={encoded_kw}&ajax=true"
        page_url = f"{_SEARCH_URL}?q={encoded_kw}"

        captured_data: dict | None = None

        try:
            async with self.deps.browserless.context(
                locale="th-TH",
                extra_http_headers={
                    "Accept-Language": "th-TH,th;q=0.9,en-US;q=0.8",
                },
                viewport={"width": 1280, "height": 800},
            ) as ctx:
                page = await ctx.new_page()

                # Intercept the AJAX catalog response
                async def _on_response(response):
                    nonlocal captured_data
                    if (
                        "catalog" in response.url
                        and "ajax=true" in response.url
                        and captured_data is None
                    ):
                        try:
                            captured_data = await response.json()
                            log.debug("lazada.api_intercepted", url=response.url[:120])
                        except Exception as exc:
                            log.debug("lazada.intercept_json_error", error=str(exc))

                page.on("response", _on_response)

                try:
                    await page.goto(
                        page_url,
                        wait_until="networkidle",
                        timeout=35_000,
                    )
                except Exception as exc:
                    log.debug("lazada.goto_timeout", error=str(exc))

                await page.close()

        except Exception as exc:
            log.warning("lazada.browserless_error", error=str(exc), keyword=keyword)
            return

        if not captured_data:
            log.warning("lazada.no_api_response_captured", keyword=keyword)
            return

        items = (captured_data.get("mods") or {}).get("listItems") or []
        if not items:
            log.info("lazada.no_items", keyword=keyword)
            return

        # Relevance filter: Lazada uses broad OR matching so results often
        # contain unrelated items. Keep only items whose title contains at
        # least one meaningful token from the search keyword.
        relevance_tokens = [t.lower() for t in keyword.split() if len(t) > 1]
        skipped = 0

        yielded = 0
        for item in items:
            if yielded >= limit:
                return
            if relevance_tokens:
                title_lower = (item.get("name", "") or "").lower()
                if not any(tok in title_lower for tok in relevance_tokens):
                    skipped += 1
                    continue
            listing = self._normalize(item)
            if listing:
                yield listing
                yielded += 1

        if skipped:
            log.info("lazada.relevance_filtered", skipped=skipped, yielded=yielded, keyword=keyword)

    async def get_detail(self, url: str) -> RawListing | None:
        return None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_price(raw) -> Decimal:
        if not raw:
            return Decimal("0")
        try:
            cleaned = re.sub(r"[^\d.]", "", str(raw))
            return Decimal(cleaned) if cleaned else Decimal("0")
        except InvalidOperation:
            return Decimal("0")

    def _normalize(self, item: dict) -> RawListing | None:
        try:
            item_id = str(item.get("itemId") or item.get("nid") or "")
            if not item_id:
                return None

            title = item.get("name", "")
            price = self._parse_price(item.get("price") or item.get("priceShow"))

            raw_desc = item.get("description")
            if isinstance(raw_desc, list):
                description: str | None = " | ".join(str(d) for d in raw_desc if d) or None
            elif raw_desc:
                description = str(raw_desc)
            else:
                description = None

            raw_url = item.get("itemUrl") or item.get("productUrl") or ""
            if raw_url.startswith("//"):
                product_url = "https:" + raw_url
            elif raw_url.startswith("/"):
                product_url = "https://www.lazada.co.th" + raw_url
            elif raw_url.startswith("http"):
                product_url = raw_url
            else:
                product_url = f"https://www.lazada.co.th/products/{item_id}.html"

            image = item.get("image", "")
            if image.startswith("//"):
                image = "https:" + image
            image_urls = [image] if image and image.startswith("http") else []

            for thumb in item.get("thumbs", []):
                img = thumb.get("url") or thumb.get("src") or ""
                if img.startswith("//"):
                    img = "https:" + img
                if img.startswith("http") and img not in image_urls:
                    image_urls.append(img)

            location = item.get("location") or None

            seller_name = item.get("sellerName") or None
            try:
                rating = float(item.get("ratingScore") or 0) or None
            except (TypeError, ValueError):
                rating = None
            try:
                review_count = int(item.get("review") or 0) or None
            except (TypeError, ValueError):
                review_count = None

            sold_txt = item.get("itemSoldCntShow") or ""
            sold_count = None
            if sold_txt:
                m = re.search(r"([\d,]+)", sold_txt)
                if m:
                    try:
                        sold_count = int(m.group(1).replace(",", ""))
                    except ValueError:
                        pass

            seller = SellerInfo(
                name=seller_name,
                rating=rating,
                review_count=review_count,
                sold_count=sold_count,
            )

            return RawListing(
                source_id=self.source_id,
                external_id=item_id,
                url=product_url,
                title=title,
                description=description,
                price=price,
                currency=Currency.THB,
                condition=Condition.UNKNOWN,
                seller=seller,
                location=location,
                image_urls=image_urls,
                posted_at=None,
                scraped_at=datetime.now(timezone.utc),
                raw_payload=item,
            )
        except Exception as exc:
            self.deps.logger.debug("lazada.normalize_error", error=str(exc))
            return None
