"""Lazada Thailand scraper.

Uses curl_cffi (Chrome TLS impersonation) with an established browser session
to access Lazada's internal AJAX catalog endpoint.  A warm-up request to the
main catalog page is made first so the session carries the required cookies.
"""
import asyncio
import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import AsyncIterator

import structlog

from shared.scraper.base import AbstractScraper, ScraperConfig
from shared.scraper.types import Condition, Currency, RawListing, SellerInfo, StructuredQuery

log = structlog.get_logger()

_SEARCH_URL = "https://www.lazada.co.th/catalog/"
_PAGE_SIZE = 40  # Lazada default items per page

_BASE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "th-TH,th;q=0.9,en-US;q=0.8",
    "Referer": "https://www.lazada.co.th/",
}

_AJAX_HEADERS = {
    **_BASE_HEADERS,
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "X-Requested-With": "XMLHttpRequest",
}


class LazadaScraper(AbstractScraper):
    source_id = "lazada"
    display_name = "Lazada Thailand"
    base_url = "https://www.lazada.co.th"
    config = ScraperConfig(tier="direct", rate_limit_rps=0.5)

    def __init__(self, deps):
        super().__init__(deps)
        self._credits_used: int = 0  # direct scraper, no paid API credits

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def search(self, query: StructuredQuery, limit: int = 50) -> AsyncIterator[RawListing]:
        from curl_cffi.requests import AsyncSession

        keyword = self.normalize_keywords(query)
        yielded = 0
        page = 1

        async with AsyncSession(impersonate="chrome124") as session:
            # Warm-up: establish a browser-like session with cookies
            try:
                await session.get(
                    f"{_SEARCH_URL}?q={keyword}",
                    headers={**_BASE_HEADERS, "Accept": "text/html,application/xhtml+xml"},
                    timeout=20,
                )
            except Exception:
                pass  # warmup failure is non-fatal

            while yielded < limit:
                params = {
                    "ajax": "true",
                    "q": keyword,
                    "page": str(page),
                    "sort": "popularity",
                }

                try:
                    r = await session.get(
                        _SEARCH_URL,
                        params=params,
                        headers=_AJAX_HEADERS,
                        timeout=25,
                    )
                    r.raise_for_status()
                    data = r.json()
                except Exception as exc:
                    self.deps.logger.warning("lazada.search_error", error=str(exc), page=page)
                    break

                items = (data.get("mods") or {}).get("listItems") or []
                if not items:
                    break

                for item in items:
                    if yielded >= limit:
                        return
                    listing = self._normalize(item)
                    if listing:
                        yield listing
                        yielded += 1

                if len(items) < _PAGE_SIZE:
                    break  # last page

                page += 1
                await asyncio.sleep(1.0 / self.config.rate_limit_rps)

    async def get_detail(self, url: str) -> RawListing | None:
        """Lazada detail pages are JS-heavy; return None and rely on search results."""
        # TODO: implement via Scrapfly render_js if needed in Phase 4+
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

            # description can be a list of bullet strings or a single string
            raw_desc = item.get("description")
            if isinstance(raw_desc, list):
                description: str | None = " | ".join(str(d) for d in raw_desc if d) or None
            elif raw_desc:
                description = str(raw_desc)
            else:
                description = None

            # Product URL — may be relative like //www.lazada.co.th/products/...
            raw_url = item.get("itemUrl") or item.get("productUrl") or ""
            if raw_url.startswith("//"):
                product_url = "https:" + raw_url
            elif raw_url.startswith("/"):
                product_url = "https://www.lazada.co.th" + raw_url
            elif raw_url.startswith("http"):
                product_url = raw_url
            else:
                product_url = f"https://www.lazada.co.th/products/{item_id}.html"

            # Images — `image` is thumbnail
            image = item.get("image", "")
            if image.startswith("//"):
                image = "https:" + image
            image_urls = [image] if image and image.startswith("http") else []

            # Also collect from `thumbs` array if available
            for thumb in item.get("thumbs", []):
                img = thumb.get("url") or thumb.get("src") or ""
                if img.startswith("//"):
                    img = "https:" + img
                if img.startswith("http") and img not in image_urls:
                    image_urls.append(img)

            location = item.get("location") or None

            # Seller
            seller_name = item.get("sellerName") or None
            try:
                rating = float(item.get("ratingScore") or 0) or None
            except (TypeError, ValueError):
                rating = None
            try:
                review_count = int(item.get("review") or 0) or None
            except (TypeError, ValueError):
                review_count = None

            # Sold count from text like "500+ sold"
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
