"""JIB Computer Group (jib.co.th) scraper.

JIB is a Thai IT retail chain selling new products. Uses curl_cffi to fetch
HTML pages and BeautifulSoup to parse product cards.

URL pattern: https://www.jib.co.th/web/product/product_list/{page}?search={keyword}
Pages are 0-indexed; each page returns up to 100 products.
"""
import asyncio
import math
import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import AsyncIterator

from shared.scraper.base import AbstractScraper, ScraperConfig
from shared.scraper.types import Condition, Currency, RawListing, SellerInfo, StructuredQuery

_BASE_URL = "https://www.jib.co.th"
_SEARCH_URL = "https://www.jib.co.th/web/product/product_list/{page}?search={keyword}"
_ITEMS_PER_PAGE = 100

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "th-TH,th;q=0.9,en-US;q=0.8",
    "Referer": "https://www.jib.co.th/",
}


class JibScraper(AbstractScraper):
    source_id = "jib"
    display_name = "JIB Computer"
    base_url = _BASE_URL
    config = ScraperConfig(tier="direct", rate_limit_rps=0.5)

    async def search(self, query: StructuredQuery, limit: int = 50) -> AsyncIterator[RawListing]:
        from curl_cffi.requests import AsyncSession
        from bs4 import BeautifulSoup

        keyword = self.normalize_keywords(query)
        pages_needed = math.ceil(limit / _ITEMS_PER_PAGE)

        # Build relevance tokens from keyword for post-fetch filtering
        relevance_tokens = [t.lower() for t in keyword.split() if len(t) > 1]

        yielded = 0

        async with AsyncSession(impersonate="chrome124") as session:
            for page in range(pages_needed):
                if yielded >= limit:
                    return

                url = _SEARCH_URL.format(page=page, keyword=keyword.replace(" ", "+"))
                try:
                    r = await session.get(url, headers=_HEADERS, timeout=20)
                    r.raise_for_status()
                except Exception as e:
                    self.deps.logger.warning("jib.fetch_error", page=page, error=str(e))
                    break

                soup = BeautifulSoup(r.text, "lxml")
                cards = soup.select(".col-xs-6.divboxpro")

                if not cards:
                    self.deps.logger.info("jib.no_cards", page=page, keyword=keyword)
                    break

                relevant_on_page = 0
                for card in cards:
                    if yielded >= limit:
                        return

                    listing = self._normalize(card)
                    if listing is None:
                        continue

                    # Relevance filter: at least one search token must appear in the title
                    title_lower = listing.title.lower()
                    if relevance_tokens and not any(tok in title_lower for tok in relevance_tokens):
                        continue

                    yield listing
                    yielded += 1
                    relevant_on_page += 1

                if relevant_on_page == 0:
                    self.deps.logger.info(
                        "jib.no_relevant_items",
                        page=page,
                        keyword=keyword,
                        total_cards=len(cards),
                    )
                    break

                await asyncio.sleep(1.0 / self.config.rate_limit_rps)

    async def get_detail(self, url: str) -> RawListing | None:
        from curl_cffi.requests import AsyncSession
        from bs4 import BeautifulSoup

        async with AsyncSession(impersonate="chrome124") as session:
            try:
                r = await session.get(url, headers=_HEADERS, timeout=20)
                r.raise_for_status()
            except Exception as e:
                self.deps.logger.warning("jib.detail_error", url=url, error=str(e))
                return None

            soup = BeautifulSoup(r.text, "lxml")
            # Product detail page: title in <h1>, price in .price_total or .price
            title_el = soup.select_one("h1.product-title, h1[class*=title], h1")
            title = title_el.get_text(strip=True) if title_el else ""

            price_el = soup.select_one(".price_total") or soup.select_one(".price")
            price_raw = price_el.get_text(strip=True) if price_el else ""
            price = _parse_price(price_raw)
            if price is None or not title:
                return None

            img = soup.select_one("#main-img, img[src*=product]")
            img_url = img.get("src", "") if img else ""
            if img_url and not img_url.startswith("http"):
                img_url = _BASE_URL + img_url

            m = re.search(r"/readProduct/(\d+)/", url)
            ext_id = m.group(1) if m else url

            return RawListing(
                source_id=self.source_id,
                external_id=ext_id,
                url=url,
                title=title,
                description=None,
                price=price,
                currency=Currency.THB,
                condition=Condition.NEW,
                seller=SellerInfo(name="JIB Computer"),
                location="ทั่วประเทศ",
                image_urls=[img_url] if img_url.startswith("http") else [],
                posted_at=None,
                scraped_at=datetime.now(timezone.utc),
                raw_payload={},
            )

    def _normalize(self, card) -> RawListing | None:
        try:
            link = card.select_one("a[href*=readProduct]")
            if not link:
                return None

            title = link.get("title", "").strip()
            url = link.get("href", "").strip()
            if not title or not url:
                return None

            m = re.search(r"/readProduct/(\d+)/", url)
            ext_id = m.group(1) if m else url

            # Discounted price first, then original price
            price_el = card.select_one(".price_total") or card.select_one(".price")
            price_raw = price_el.get_text(strip=True) if price_el else ""
            price = _parse_price(price_raw)
            if price is None:
                return None

            img = card.select_one("img")
            img_src = img.get("src", "") if img else ""
            if img_src and not img_src.startswith("http"):
                img_src = _BASE_URL + img_src

            return RawListing(
                source_id=self.source_id,
                external_id=ext_id,
                url=url,
                title=title,
                description=None,
                price=price,
                currency=Currency.THB,
                condition=Condition.NEW,
                seller=SellerInfo(name="JIB Computer"),
                location="ทั่วประเทศ",
                image_urls=[img_src] if img_src.startswith("http") else [],
                posted_at=None,
                scraped_at=datetime.now(timezone.utc),
                raw_payload={"ext_id": ext_id},
            )
        except Exception as e:
            self.deps.logger.debug("jib.normalize_error", error=str(e))
            return None


def _parse_price(raw: str) -> Decimal | None:
    """Parse Thai price string like '13,990.-' or '฿13,990' → Decimal."""
    cleaned = re.sub(r"[^\d.]", "", raw)
    # Remove trailing dot if it's just a formatting dot
    cleaned = cleaned.rstrip(".")
    if not cleaned:
        return None
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None
