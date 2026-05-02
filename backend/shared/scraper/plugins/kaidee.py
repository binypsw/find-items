"""Kaidee.com scraper — uses Next.js SSR data endpoint.

Kaidee is a Next.js app; listings are served via /_next/data/{buildId}/en/browse.json.
We fetch the build ID from the homepage on first call and cache it; on staleness (404)
we re-discover it automatically.
"""
import asyncio
import math
import re
from datetime import datetime, timezone
from decimal import Decimal
from typing import AsyncIterator

from shared.scraper.base import AbstractScraper, ScraperConfig
from shared.scraper.types import Condition, Currency, RawListing, SellerInfo, StructuredQuery

BANGKOK_TZ = timezone.utc  # store all times in UTC

_CONDITION_MAP = {
    "มือสอง": Condition.USED,
    "used": Condition.USED,
    "มือหนึ่ง": Condition.NEW,
    "new": Condition.NEW,
    "ใหม่": Condition.NEW,
    "refurbished": Condition.REFURBISHED,
}

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "th-TH,th;q=0.9,en-US;q=0.8",
    "Referer": "https://www.kaidee.com/",
}

_PAGE_SIZE = 24  # Kaidee returns 24 ads per page


class KaideeScraper(AbstractScraper):
    source_id = "kaidee"
    display_name = "Kaidee.com"
    base_url = "https://www.kaidee.com"
    config = ScraperConfig(tier="direct", rate_limit_rps=0.5)

    _build_id: str | None = None  # class-level cache; refreshed on 404

    async def _get_build_id(self, session) -> str:
        """Fetch the Next.js build ID from the Kaidee homepage."""
        r = await session.get(
            "https://www.kaidee.com/",
            headers={**_HEADERS, "Accept": "text/html,application/xhtml+xml"},
            timeout=20,
        )
        r.raise_for_status()
        m = re.search(r'"buildId":"([^"]+)"', r.text)
        if not m:
            raise RuntimeError("Could not find Kaidee buildId in homepage")
        bid = m.group(1)
        KaideeScraper._build_id = bid
        return bid

    async def search(self, query: StructuredQuery, limit: int = 50) -> AsyncIterator[RawListing]:
        from curl_cffi.requests import AsyncSession

        keyword = self.normalize_keywords(query)
        pages = math.ceil(limit / _PAGE_SIZE)
        yielded = 0

        async with AsyncSession(impersonate="chrome124") as session:
            # Ensure we have a build ID
            build_id = KaideeScraper._build_id or await self._get_build_id(session)

            for page in range(1, pages + 1):
                params = {"keyword": keyword, "page": str(page)}
                if query.max_price_thb:
                    params["price_end"] = str(int(query.max_price_thb))
                if query.min_price_thb:
                    params["price_start"] = str(int(query.min_price_thb))

                url = f"https://www.kaidee.com/_next/data/{build_id}/en/browse.json"

                try:
                    r = await session.get(
                        url,
                        params=params,
                        headers={**_HEADERS, "Accept": "application/json", "x-nextjs-data": "1"},
                        timeout=20,
                    )
                    # Build ID may have changed — refresh and retry once
                    if r.status_code == 404:
                        self.deps.logger.info("kaidee.build_id_stale", old_id=build_id)
                        build_id = await self._get_build_id(session)
                        url = f"https://www.kaidee.com/_next/data/{build_id}/en/browse.json"
                        r = await session.get(
                            url,
                            params=params,
                            headers={**_HEADERS, "Accept": "application/json", "x-nextjs-data": "1"},
                            timeout=20,
                        )
                    r.raise_for_status()
                    data = r.json()
                except Exception as e:
                    self.deps.logger.warning("kaidee.search_error", page=page, error=str(e), source_id=self.source_id)
                    break

                ads = data.get("pageProps", {}).get("ads", [])
                if not ads:
                    break

                for item in ads:
                    if yielded >= limit:
                        return
                    listing = self._normalize(item)
                    if listing:
                        yield listing
                        yielded += 1

                await asyncio.sleep(1.0 / self.config.rate_limit_rps)

    async def get_detail(self, url: str) -> RawListing | None:
        """Fetch detail page via SSR HTML — used for full description."""
        from curl_cffi.requests import AsyncSession

        async with AsyncSession(impersonate="chrome124") as session:
            # Ensure build ID
            build_id = KaideeScraper._build_id or await self._get_build_id(session)

            # Extract listing ID from URL: https://www.kaidee.com/post/12345678-slug
            m = re.search(r"/post/(\d+)", url)
            if not m:
                return None
            ad_id = m.group(1)

            detail_url = f"https://www.kaidee.com/_next/data/{build_id}/en/post/{ad_id}.json"
            try:
                r = await session.get(
                    detail_url,
                    headers={**_HEADERS, "Accept": "application/json", "x-nextjs-data": "1"},
                    timeout=20,
                )
                if r.status_code == 404:
                    build_id = await self._get_build_id(session)
                    detail_url = f"https://www.kaidee.com/_next/data/{build_id}/en/post/{ad_id}.json"
                    r = await session.get(
                        detail_url,
                        headers={**_HEADERS, "Accept": "application/json", "x-nextjs-data": "1"},
                        timeout=20,
                    )
                r.raise_for_status()
                data = r.json()
                ad = data.get("pageProps", {}).get("ad", {})
                return self._normalize(ad) if ad else None
            except Exception as e:
                self.deps.logger.warning("kaidee.detail_error", url=url, error=str(e))
                return None

    def _normalize(self, item: dict) -> RawListing | None:
        try:
            # Price
            price_raw = item.get("price", 0)
            if isinstance(price_raw, str):
                price_raw = re.sub(r"[^\d.]", "", price_raw) or "0"
            price = Decimal(str(price_raw or 0))

            # External ID
            ext_id = str(item.get("id", ""))
            if not ext_id:
                return None

            # Construct canonical URL
            title_slug = re.sub(r"[^a-z0-9]+", "-", (item.get("title") or "").lower()).strip("-")[:60]
            item_url = f"https://www.kaidee.com/post/{ext_id}-{title_slug}" if title_slug else f"https://www.kaidee.com/post/{ext_id}"

            # Condition
            cond_raw = str(item.get("conditionName", item.get("condition", ""))).strip()
            condition = _CONDITION_MAP.get(cond_raw, Condition.UNKNOWN)

            # Location
            location = item.get("location") or None
            if isinstance(location, dict):
                location = location.get("name_th", location.get("name_en"))

            # Images — `image` is the primary thumbnail; `images` array for detail
            images = item.get("images", [])
            primary = item.get("image", "")
            if isinstance(images, list) and images:
                image_urls = [img.get("original", img) if isinstance(img, dict) else str(img) for img in images]
            elif primary:
                image_urls = [primary]
            else:
                image_urls = []

            # Seller info
            member = item.get("member", {}) or {}
            seller = SellerInfo(
                name=member.get("name"),
                rating=member.get("rating"),
            )

            # Posted timestamp
            posted_at = None
            if ts := item.get("firstApprovedTime", item.get("insertedAt")):
                try:
                    posted_at = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                except Exception:
                    pass

            return RawListing(
                source_id=self.source_id,
                external_id=ext_id,
                url=item_url,
                title=item.get("title", ""),
                description=item.get("description"),
                price=price,
                currency=Currency.THB,
                condition=condition,
                seller=seller,
                location=location,
                image_urls=[u for u in image_urls if isinstance(u, str) and u.startswith("http")],
                posted_at=posted_at,
                scraped_at=datetime.now(BANGKOK_TZ),
                raw_payload=item,
            )
        except Exception as e:
            self.deps.logger.debug("kaidee.normalize_error", error=str(e))
            return None
