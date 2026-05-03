"""BNN (bnn.in.th) scraper — Thai IT retail store.

BNN is a Thai electronics/IT retailer (part of Com7 group).
Their search page is server-side rendered Nuxt.js, so curl_cffi can
fetch plain HTML without requiring a real browser.

Credit cost: 0 (direct HTTP, no paid proxy).
"""
import re
import urllib.parse
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import AsyncIterator

import structlog

from shared.scraper.base import AbstractScraper, ScraperConfig
from shared.scraper.types import Condition, Currency, RawListing, SellerInfo, StructuredQuery

log = structlog.get_logger()

_BASE_URL = "https://www.bnn.in.th"
_SEARCH_URL = "https://www.bnn.in.th/th/p"


def _parse_price(raw: str) -> Decimal | None:
    """Strip Thai baht symbol, commas, spaces and parse as Decimal."""
    cleaned = re.sub(r"[^\d.]", "", raw)
    cleaned = cleaned.rstrip(".")
    if not cleaned:
        return None
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


class BnnScraper(AbstractScraper):
    source_id = "bnn"
    display_name = "BNN"
    base_url = _BASE_URL
    config = ScraperConfig(tier="direct", rate_limit_rps=0.5)

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def normalize_keywords(self, query: StructuredQuery) -> str:
        """BNN works best with English product terms — skip Thai raw_query
        which may include condition words (มือสอง, ใหม่) that confuse the search.
        Prefer English keywords, then fall back to Thai, then raw_query."""
        if query.keywords_en:
            return " ".join(query.keywords_en).strip()
        if query.keywords_th:
            return " ".join(query.keywords_th).strip()
        if query.keywords:
            return " ".join(query.keywords).strip()
        return (query.raw_query or "").strip()

    def _keyword_fallbacks(self, query: StructuredQuery) -> list[str]:
        """Return a list of keyword strings to try in order (most specific → broadest).

        BNN's search engine uses AND matching — too many specific terms can return 0 results.
        We progressively drop keywords until we get results or exhaust fallbacks.
        """
        base = self.normalize_keywords(query)
        tokens = base.split()
        fallbacks = []
        # Full keyword set (e.g. "DDR4 3600 16GB")
        fallbacks.append(base)
        # Drop last token progressively (e.g. "DDR4 3600", "DDR4")
        for i in range(len(tokens) - 1, 0, -1):
            candidate = " ".join(tokens[:i])
            if candidate and candidate not in fallbacks:
                fallbacks.append(candidate)
        return fallbacks

    async def _fetch_cards(self, curl_req, keyword: str, BeautifulSoup):
        """Fetch BNN search page and return parsed cards list."""
        params = urllib.parse.urlencode({"q": keyword})
        url = f"{_SEARCH_URL}?{params}"
        log.info("bnn.search", keyword=keyword, url=url)
        try:
            resp = curl_req.get(
                url,
                impersonate="chrome124",
                timeout=20,
                headers={
                    "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
                    "Accept-Language": "th-TH,th;q=0.9,en-US;q=0.8",
                    "Referer": _BASE_URL,
                },
            )
        except Exception as exc:
            log.warning("bnn.fetch_error", error=str(exc), keyword=keyword)
            return []
        if resp.status_code != 200:
            log.warning("bnn.bad_status", status=resp.status_code, keyword=keyword)
            return []
        soup = BeautifulSoup(resp.text, "lxml")
        return soup.select("a.product-item")

    async def search(self, query: StructuredQuery, limit: int = 50) -> AsyncIterator[RawListing]:
        try:
            from curl_cffi import requests as curl_req
            from bs4 import BeautifulSoup
        except ImportError as exc:
            log.error("bnn.missing_dependency", error=str(exc))
            return

        # Build relevance tokens from the original full keyword for post-filtering
        full_keyword = self.normalize_keywords(query)
        relevance_tokens = [t.lower() for t in full_keyword.split() if len(t) > 1]

        # Try keyword fallbacks until we find relevant items.
        # Each fallback is progressively broader — we stop at the first one that
        # produces at least one relevant listing (passing the relevance filter).
        yielded = 0
        skipped = 0
        keyword_used = full_keyword

        for kw in self._keyword_fallbacks(query):
            if yielded >= limit:
                break

            cards = await self._fetch_cards(curl_req, kw, BeautifulSoup)
            if not cards:
                continue

            fallback_yielded = 0
            fallback_skipped = 0
            pending: list = []

            for card in cards:
                if yielded + fallback_yielded >= limit:
                    break
                listing = self._normalize(card)
                if listing is None:
                    continue
                if relevance_tokens:
                    title_lower = listing.title.lower()
                    if not any(tok in title_lower for tok in relevance_tokens):
                        fallback_skipped += 1
                        continue
                pending.append(listing)
                fallback_yielded += 1

            if fallback_yielded > 0:
                # This keyword level produced relevant results — yield and stop
                keyword_used = kw
                log.info("bnn.keyword_resolved", keyword=kw, cards=len(cards), yielding=fallback_yielded)
                for listing in pending:
                    yield listing
                    yielded += 1
                skipped += fallback_skipped
                break
            # else: keep trying broader fallback keywords

        if yielded == 0:
            log.info("bnn.no_items", keyword=full_keyword)
        if skipped:
            log.info("bnn.relevance_filtered", skipped=skipped, yielded=yielded, keyword=keyword_used)

    async def get_detail(self, url: str) -> RawListing | None:
        return None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _normalize(self, card) -> RawListing | None:
        """Convert a BeautifulSoup card element to a RawListing."""
        try:
            # URL — strip query string to get clean product URL
            raw_href = card.get("href", "")
            parsed = urllib.parse.urlparse(raw_href)
            clean_path = parsed.path  # e.g. /th/p/kingston-fury-beast-ddr4-...
            product_url = _BASE_URL + clean_path

            # External ID — short alphanumeric code after last underscore in slug
            slug = clean_path.split("/")[-1]
            id_match = re.search(r"_([a-z0-9]+)$", slug)
            external_id = id_match.group(1) if id_match else slug[:40]

            if not external_id:
                return None

            # Title — prefer data attribute to avoid whitespace noise
            name_el = card.select_one(".product-name")
            if not name_el:
                return None
            title = (name_el.get("title") or name_el.get_text(" ", strip=True)).strip()
            if not title:
                return None

            # Price
            price_el = card.select_one(".product-price")
            price_text = price_el.get_text(strip=True) if price_el else ""
            price = _parse_price(price_text)
            if price is None or price <= 0:
                return None

            # Image — class="image" is the product photo; skip label images
            img_el = card.select_one("img.image")
            image_urls = []
            if img_el:
                src = img_el.get("src", "")
                if src.startswith("http"):
                    image_urls.append(src)

            # Brand (shown in image container header)
            brand_el = card.select_one(".product-label-brand")
            brand = brand_el.get_text(strip=True) if brand_el else None

            return RawListing(
                source_id=self.source_id,
                external_id=external_id,
                url=product_url,
                title=title,
                description=None,
                price=price,
                currency=Currency.THB,
                condition=Condition.NEW,  # BNN is a retail store — all new
                seller=SellerInfo(name=brand or self.display_name),
                location=None,
                image_urls=image_urls,
                posted_at=None,
                scraped_at=datetime.now(timezone.utc),
                raw_payload={
                    "href": raw_href,
                    "slug": slug,
                    "brand": brand,
                    "price_text": price_text,
                },
            )
        except Exception as exc:
            log.debug("bnn.normalize_error", error=str(exc))
            return None
