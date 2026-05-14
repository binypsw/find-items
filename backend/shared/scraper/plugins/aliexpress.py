"""AliExpress Thailand scraper.

Uses Playwright headless Chromium to load the search page (bxpunish anti-bot
blocks plain curl_cffi), then parses the rendered HTML with BeautifulSoup.

Items on AliExpress are new-only — condition is always Condition.NEW.
"""
import re
import urllib.parse
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import AsyncIterator

import structlog
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

from shared.scraper.base import AbstractScraper, ScraperConfig
from shared.scraper.relevance import calc_min_match, normalize_title
from shared.scraper.types import Condition, Currency, RawListing, SellerInfo, StructuredQuery

log = structlog.get_logger()

_BASE_URL = "https://th.aliexpress.com"
_SEARCH_URL = "https://th.aliexpress.com/w/wholesale-{slug}.html"
_MAX_PAGES = 3


class AliExpressScraper(AbstractScraper):
    source_id = "aliexpress"
    display_name = "AliExpress"
    base_url = _BASE_URL
    config = ScraperConfig(tier="browser_headless", rate_limit_rps=0.2)

    def normalize_keywords(self, query: StructuredQuery) -> str:
        """AliExpress works best with English product terms."""
        if query.keywords_en:
            return " ".join(query.keywords_en).strip()
        if query.keywords_th:
            return " ".join(query.keywords_th).strip()
        if query.keywords:
            return " ".join(query.keywords).strip()
        return (query.raw_query or "").strip()

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def search(self, query: StructuredQuery, limit: int = 50) -> AsyncIterator[RawListing]:
        keyword = self.normalize_keywords(query)
        slug = re.sub(r"\s+", "-", keyword.strip().lower())
        slug = urllib.parse.quote(slug, safe="-")

        if query.keywords_en:
            relevance_tokens = [t.lower() for t in query.keywords_en if len(t) > 1]
        elif query.keywords:
            relevance_tokens = [t.lower() for t in query.keywords if len(t) > 1]
        else:
            relevance_tokens = [t.lower() for t in keyword.split() if len(t) > 1]

        min_match = calc_min_match(relevance_tokens) if relevance_tokens else 1

        def _is_relevant(title: str) -> bool:
            if not relevance_tokens:
                return True
            tl = normalize_title(title)
            return sum(1 for tok in relevance_tokens if tok in tl) >= min_match

        yielded = 0
        skipped = 0

        try:
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(headless=True)
                try:
                    ctx = None
                    try:
                        ctx = await browser.new_context(
                            locale="th-TH",
                            extra_http_headers={"Accept-Language": "th-TH,th;q=0.9,en-US;q=0.8"},
                            viewport={"width": 1280, "height": 900},
                        )
                        page = await ctx.new_page()

                        for page_num in range(1, _MAX_PAGES + 1):
                            if yielded >= limit:
                                break

                            base_url = _SEARCH_URL.format(slug=slug)
                            if page_num > 1:
                                sep = "&" if "?" in base_url else "?"
                                url = f"{base_url}{sep}page={page_num}"
                            else:
                                url = base_url

                            log.info("aliexpress.search", keyword=keyword, page=page_num, url=url)

                            try:
                                await page.goto(url, wait_until="networkidle", timeout=35_000)
                            except Exception as exc:
                                log.debug("aliexpress.goto_timeout", error=str(exc), page=page_num)

                            try:
                                await page.wait_for_selector(
                                    ".search-item-card-wrapper-gallery",
                                    timeout=8_000,
                                )
                            except Exception:
                                pass

                            html = await page.content()
                            soup = BeautifulSoup(html, "lxml")

                            cards = soup.select(".search-item-card-wrapper-gallery")
                            if not cards:
                                log.debug("aliexpress.no_cards_primary", page=page_num, keyword=keyword)
                                break

                            page_yielded = 0
                            for card in cards:
                                if yielded >= limit:
                                    break
                                item = self._extract_card(card)
                                if item is None:
                                    continue
                                if item["title"] and not _is_relevant(item["title"]):
                                    skipped += 1
                                    continue
                                listing = self._normalize(item)
                                if listing:
                                    yield listing
                                    yielded += 1
                                    page_yielded += 1

                            log.info(
                                "aliexpress.page_done",
                                page=page_num,
                                page_yielded=page_yielded,
                                total_yielded=yielded,
                                keyword=keyword,
                            )

                            if page_yielded == 0:
                                break

                    finally:
                        if ctx:
                            await ctx.close()
                finally:
                    await browser.close()

        except Exception as exc:
            log.warning("aliexpress.browser_error", error=str(exc), keyword=keyword)
            return

        if skipped:
            log.info("aliexpress.relevance_filtered", skipped=skipped, yielded=yielded, keyword=keyword)
        if yielded == 0:
            log.info("aliexpress.no_items", keyword=keyword)

    async def get_detail(self, url: str) -> RawListing | None:
        return None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _extract_card(self, card) -> dict | None:
        try:
            link_el = card.select_one("a.search-card-item[href]")
            if not link_el:
                link_el = card.select_one("a[href*='/item/']")
            if not link_el:
                return None

            raw_href = link_el.get("href", "")
            if not raw_href:
                return None

            title_el = card.select_one("h3.k7_kw")
            if not title_el:
                title_el = card.select_one("h1")
            if not title_el:
                title_el = card.select_one("span[dir='auto']")
            if not title_el:
                title_el = card.select_one("[class*='title']")
            title = title_el.get_text(strip=True) if title_el else ""

            price_str = ""
            price_el = card.select_one("div.k7_ea[aria-label]")
            if price_el:
                price_str = price_el.get("aria-label", "") or price_el.get_text(strip=True)
            if not price_str:
                price_el = card.select_one("[class*='price']")
                if price_el:
                    price_str = price_el.get_text(strip=True)

            img_el = card.select_one("img.product-img[src]")
            if not img_el:
                img_el = card.select_one("img[src]")
            image = img_el.get("src", "") if img_el else ""

            sold_el = card.select_one("div.k7_s7")
            if not sold_el:
                sold_el = card.select_one("[class*='sold']")
            sold_str = sold_el.get_text(strip=True) if sold_el else ""

            return {
                "href": raw_href,
                "title": title,
                "price_str": price_str,
                "image": image,
                "sold_str": sold_str,
            }
        except Exception as exc:
            log.debug("aliexpress.extract_card_error", error=str(exc))
            return None

    @staticmethod
    def _parse_price(price_str: str) -> Decimal:
        if not price_str:
            return Decimal("0")
        cleaned = re.sub(r"[^\d.]", "", price_str.replace(",", ""))
        try:
            return Decimal(cleaned) if cleaned else Decimal("0")
        except InvalidOperation:
            return Decimal("0")

    @staticmethod
    def _normalize_url(raw: str) -> str:
        if raw.startswith("//"):
            return "https:" + raw
        if raw.startswith("/"):
            return _BASE_URL + raw
        if raw.startswith("http"):
            return raw
        return raw

    @staticmethod
    def _extract_external_id(url: str) -> str:
        m = re.search(r"/item/(\d+)\.html", url)
        if m:
            return m.group(1)
        m = re.search(r"/item/(\d+)", url)
        if m:
            return m.group(1)
        parsed = urllib.parse.urlparse(url)
        return re.sub(r"[^a-z0-9]", "_", parsed.path.strip("/"))[:64] or url[-40:]

    def _normalize(self, item: dict) -> RawListing | None:
        try:
            product_url = self._normalize_url(item["href"])
            external_id = self._extract_external_id(product_url)
            if not external_id:
                return None

            title = item.get("title", "").strip()
            if not title:
                return None

            price = self._parse_price(item.get("price_str", ""))

            image = item.get("image", "")
            if image.startswith("//"):
                image = "https:" + image
            image_urls = [image] if image and image.startswith("http") else []

            sold_count = None
            sold_str = item.get("sold_str", "")
            if sold_str:
                m = re.search(r"([\d,]+)", sold_str)
                if m:
                    try:
                        sold_count = int(m.group(1).replace(",", ""))
                    except ValueError:
                        pass

            return RawListing(
                source_id=self.source_id,
                external_id=external_id,
                url=product_url,
                title=title,
                description=None,
                price=price,
                currency=Currency.THB,
                condition=Condition.NEW,
                seller=SellerInfo(sold_count=sold_count),
                location=None,
                image_urls=image_urls,
                posted_at=None,
                scraped_at=datetime.now(timezone.utc),
                raw_payload=item,
            )
        except Exception as exc:
            log.debug("aliexpress.normalize_error", error=str(exc))
            return None
