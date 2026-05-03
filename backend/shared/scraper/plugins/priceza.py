"""Priceza (priceza.com) scraper — Thai price comparison aggregator.

Priceza aggregates prices from many Thai retail stores (JIB, BNN, Advice,
IT City, Power Buy, etc.) and shows the cheapest-available new price per
product. Returns product group pages (not individual store listings), so
each result represents the best current price from any store Priceza tracks.

URL pattern: /s/ราคา/{keyword-lowercased-hyphenated}

Credit cost: 0 (direct HTML, no paid proxy).
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

_BASE_URL = "https://www.priceza.com"
_SEARCH_BASE = "https://www.priceza.com/s/ราคา"


def _keyword_to_slug(keyword: str) -> str:
    """Convert search keyword to Priceza URL slug: lowercase, spaces → hyphens."""
    return re.sub(r"\s+", "-", keyword.strip().lower())


def _parse_min_price(text: str) -> Decimal | None:
    """Extract minimum price from range text like '฿1,450 -฿7,150'."""
    m = re.search(r"฿([\d,]+)", text)
    if not m:
        return None
    try:
        return Decimal(m.group(1).replace(",", ""))
    except InvalidOperation:
        return None


class PricezaScraper(AbstractScraper):
    source_id = "priceza"
    display_name = "Priceza"
    base_url = _BASE_URL
    config = ScraperConfig(tier="direct", rate_limit_rps=0.3)

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def normalize_keywords(self, query: StructuredQuery) -> str:
        """Prefer English keywords for Priceza (most Thai stores list in English)."""
        if query.keywords_en:
            return " ".join(query.keywords_en).strip()
        if query.keywords_th:
            return " ".join(query.keywords_th).strip()
        if query.keywords:
            return " ".join(query.keywords).strip()
        return (query.raw_query or "").strip()

    async def search(self, query: StructuredQuery, limit: int = 50) -> AsyncIterator[RawListing]:
        try:
            from curl_cffi import requests as curl_req
            from bs4 import BeautifulSoup
        except ImportError as exc:
            log.error("priceza.missing_dependency", error=str(exc))
            return

        keyword = self.normalize_keywords(query)
        slug = _keyword_to_slug(keyword)
        url = f"{_SEARCH_BASE}/{urllib.parse.quote(slug, safe='-')}"

        log.info("priceza.search", keyword=keyword, url=url)

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
            log.warning("priceza.fetch_error", error=str(exc), keyword=keyword)
            return

        if resp.status_code != 200:
            log.warning("priceza.bad_status", status=resp.status_code, keyword=keyword)
            return

        soup = BeautifulSoup(resp.text, "lxml")
        items = soup.select(".pz-pdb-item-info")

        if not items:
            log.info("priceza.no_items", keyword=keyword)
            return

        # Relevance filter: require title to contain majority of keyword tokens
        tokens = [t.lower() for t in keyword.split() if len(t) > 1]
        min_match = max(1, len(tokens) // 2) if tokens else 0

        skipped = 0
        yielded = 0

        for item in items:
            if yielded >= limit:
                break

            listing = self._normalize(item)
            if listing is None:
                continue

            if tokens:
                title_lower = listing.title.lower()
                matched = sum(1 for tok in tokens if tok in title_lower)
                if matched < min_match:
                    skipped += 1
                    continue

            yield listing
            yielded += 1

        if skipped:
            log.info("priceza.relevance_filtered", skipped=skipped, yielded=yielded, keyword=keyword)

    async def get_detail(self, url: str) -> RawListing | None:
        return None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _normalize(self, item) -> RawListing | None:
        try:
            product_path = item.get("data-product-url", "")
            if not product_path:
                return None

            product_url = _BASE_URL + product_path

            # External ID from URL slug ending digit string
            id_match = re.search(r"-(\d{6,})$", product_path)
            external_id = id_match.group(1) if id_match else product_path.split("/")[-1][:40]
            if not external_id:
                return None

            # Title: strip leading "ราคา " prefix that Priceza adds
            name_el = item.select_one(".pz-pdb_name")
            if not name_el:
                return None
            raw_title = name_el.get("title", "") or name_el.get_text(" ", strip=True)
            title = re.sub(r"^ราคา\s+", "", raw_title).strip()
            if not title:
                return None

            # Price: minimum of range or exact price.
            # Two variants exist: single price <span class="pz-pdb-price">฿3,550</span>
            # and range <span class="pz-pdb-price pd-group">฿1,450 -฿7,150</span>
            price_el = item.select_one(".pz-pdb-price")
            price_text = price_el.get_text(strip=True) if price_el else ""
            price = _parse_min_price(price_text)
            if price is None or price <= 0:
                return None

            # Image
            img_el = item.select_one("img.pz-pdb_media--img")
            image_urls = []
            if img_el:
                src = img_el.get("src", "")
                if src.startswith("http") and "default.svg" not in src:
                    image_urls.append(src)

            # Number of store offers (from "เปรียบเทียบราคา (N)" button)
            offer_btn = item.select_one("[class*=pz-btn-product-group], [class*=btn-compare]")
            offer_count = None
            if offer_btn:
                m = re.search(r"\((\d+)\)", offer_btn.get_text())
                offer_count = int(m.group(1)) if m else None

            return RawListing(
                source_id=self.source_id,
                external_id=external_id,
                url=product_url,
                title=title,
                description=None,
                price=price,
                currency=Currency.THB,
                # Priceza aggregates retail stores — treat as new
                condition=Condition.NEW,
                seller=SellerInfo(name=self.display_name),
                location=None,
                image_urls=image_urls,
                posted_at=None,
                scraped_at=datetime.now(timezone.utc),
                raw_payload={
                    "price_range": price_text,
                    "offer_count": offer_count,
                    "product_path": product_path,
                },
            )
        except Exception as exc:
            log.debug("priceza.normalize_error", error=str(exc))
            return None
