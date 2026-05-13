"""Facebook Marketplace Bangkok scraper.

Searches Facebook Marketplace (Bangkok area, no-login mode) by loading the
SSR HTML via headless Playwright and extracting the embedded Relay JSON blob.

Facebook embeds up to ~24 listings per page in a <script type="application/json">
tag containing "CometMarketplaceSearchContentContainerQueryRelayPreloader".
No authentication is required for this first page of results.

All listings on Facebook Marketplace are used/second-hand — condition is
hardcoded to USED.

Rate limit: 0.1 rps (one request every ~10 s) — home server, no login.
"""
import json
import re
import urllib.parse
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import AsyncIterator

import structlog
from playwright.async_api import async_playwright

from shared.scraper.base import AbstractScraper, ScraperConfig
from shared.scraper.relevance import calc_min_match, normalize_title
from shared.scraper.types import Condition, Currency, RawListing, SellerInfo, StructuredQuery

log = structlog.get_logger()

_SEARCH_URL = "https://www.facebook.com/marketplace/bangkok/search/?query={keyword}"
_ITEM_URL = "https://www.facebook.com/marketplace/item/{listing_id}/"

# Relay SSR blob identifier — present in the script tag that holds listing data
_RELAY_MARKER = "CometMarketplaceSearchContentContainerQueryRelayPreloader"


class FacebookMarketplaceScraper(AbstractScraper):
    source_id = "facebook"
    display_name = "Facebook Marketplace"
    base_url = "https://www.facebook.com/marketplace"
    config = ScraperConfig(tier="browser_headless", rate_limit_rps=0.1)

    def normalize_keywords(self, query: StructuredQuery) -> str:
        # Prefer raw_query (user's exact input) — covers Thai/English mix.
        # Fall back to English keywords before Thai because Facebook Marketplace
        # catalog titles are mostly in English/transliteration for electronics.
        if query.raw_query:
            return query.raw_query.strip()
        if query.keywords_en:
            return " ".join(query.keywords_en).strip()
        if query.keywords_th:
            return " ".join(query.keywords_th).strip()
        return super().normalize_keywords(query)

    async def search(self, query: StructuredQuery, limit: int = 50) -> AsyncIterator[RawListing]:
        keyword = self.normalize_keywords(query)
        url = _SEARCH_URL.format(keyword=_url_encode(keyword))

        # Build relevance tokens from keywords_en when available (same pattern
        # as lazada.py / jib.py) — fall back to raw keyword split.
        if query.keywords_en:
            relevance_tokens = [t.lower() for t in query.keywords_en if len(t) > 1]
        elif query.keywords_th:
            relevance_tokens = [t.lower() for t in query.keywords_th if len(t) > 1]
        elif query.keywords:
            relevance_tokens = [t.lower() for t in query.keywords if len(t) > 1]
        else:
            relevance_tokens = [t.lower() for t in keyword.split() if len(t) > 1]

        min_match = calc_min_match(relevance_tokens)

        def _is_relevant(title: str) -> bool:
            tl = normalize_title(title)
            return sum(1 for tok in relevance_tokens if tok in tl) >= min_match

        html: str = ""
        try:
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(headless=True)
                try:
                    ctx = await browser.new_context(
                        locale="th-TH",
                        extra_http_headers={"Accept-Language": "th-TH,th;q=0.9,en-US;q=0.8"},
                        viewport={"width": 1280, "height": 900},
                    )
                    page = await ctx.new_page()
                    try:
                        await page.goto(url, wait_until="networkidle", timeout=35_000)
                    except Exception as exc:
                        log.debug("facebook.goto_timeout", error=str(exc))
                    html = await page.content()
                    await ctx.close()
                finally:
                    await browser.close()
        except Exception as exc:
            log.warning("facebook.browser_error", error=str(exc), keyword=keyword)
            return

        edges = _extract_edges(html)
        if not edges:
            log.warning("facebook.no_edges_found", keyword=keyword, url=url)
            return

        log.info("facebook.edges_found", count=len(edges), keyword=keyword)

        yielded = 0
        skipped = 0

        for edge in edges:
            if yielded >= limit:
                return
            listing_node = _safe_get(edge, "node", "listing")
            if listing_node is None:
                continue

            # Skip sold or pending listings
            if listing_node.get("is_sold") or listing_node.get("is_pending"):
                continue

            title = listing_node.get("marketplace_listing_title", "") or ""
            if not title:
                continue

            if not _is_relevant(title):
                skipped += 1
                continue

            raw_listing = _normalize(listing_node, self.source_id)
            if raw_listing is not None:
                yield raw_listing
                yielded += 1

        if skipped:
            log.info(
                "facebook.relevance_filtered",
                skipped=skipped,
                yielded=yielded,
                keyword=keyword,
            )

    async def get_detail(self, url: str) -> RawListing | None:
        # Detail page requires login for most data — not implemented.
        return None


# ---------------------------------------------------------------------------
# Relay JSON extraction helpers
# ---------------------------------------------------------------------------

def _extract_edges(html: str) -> list[dict]:
    """Find the Relay SSR JSON blob in the page HTML and extract listing edges.

    Facebook embeds one or more <script type="application/json"> tags; we find
    the one containing the Relay marker and then navigate the nested bbox
    structure to reach marketplace_search.feed_units.edges.
    """
    # Extract all <script type="application/json"> contents
    script_contents = re.findall(
        r'<script\s+type="application/json"[^>]*>(.*?)</script>',
        html,
        re.DOTALL,
    )

    relay_blob: dict | None = None
    for content in script_contents:
        if _RELAY_MARKER in content:
            try:
                relay_blob = json.loads(content)
                break
            except json.JSONDecodeError as exc:
                log.debug("facebook.json_decode_error", error=str(exc))
                continue

    if relay_blob is None:
        log.debug("facebook.relay_blob_not_found")
        return []

    return _find_edges(relay_blob)


def _find_edges(data: dict) -> list[dict]:
    """Navigate Relay SSR JSON to find marketplace feed_units edges.

    Tries multiple known path variants since Relay nesting depth varies by
    Facebook deploy / A/B experiment.
    """
    # Each path is a list of alternating dict-keys and list-indices.
    # The final element must resolve to the edges list.
    paths_to_try = [
        # Primary path observed in research
        [
            "require", 0, 3, 0, "__bbox",
            "require", 0, 3, 1, "__bbox",
            "result", "data", "marketplace_search", "feed_units", "edges",
        ],
        # Alternate: outer require index 1
        [
            "require", 0, 3, 1, "__bbox",
            "result", "data", "marketplace_search", "feed_units", "edges",
        ],
        # Alternate: some deploys skip first bbox level
        [
            "require", 0, 3, 0, "__bbox",
            "result", "data", "marketplace_search", "feed_units", "edges",
        ],
        # Alternate: require index 1 at top
        [
            "require", 1, 3, 0, "__bbox",
            "result", "data", "marketplace_search", "feed_units", "edges",
        ],
    ]

    for path in paths_to_try:
        try:
            node = data
            for key in path:
                node = node[key]  # type: ignore[index]
            if isinstance(node, list):
                log.debug("facebook.edges_path_matched", path=str(path[:6]))
                return node  # type: ignore[return-value]
        except (KeyError, IndexError, TypeError):
            continue

    # Last resort: recursive search for the edges list
    return _recursive_find_edges(data)


def _recursive_find_edges(node, depth: int = 0) -> list[dict]:
    """Recursively walk the Relay blob looking for feed_units.edges."""
    if depth > 12:
        return []
    if isinstance(node, dict):
        if "feed_units" in node:
            edges = _safe_get(node, "feed_units", "edges")
            if isinstance(edges, list) and edges:
                return edges
        for value in node.values():
            result = _recursive_find_edges(value, depth + 1)
            if result:
                return result
    elif isinstance(node, list):
        for item in node:
            result = _recursive_find_edges(item, depth + 1)
            if result:
                return result
    return []


# ---------------------------------------------------------------------------
# Listing normalization
# ---------------------------------------------------------------------------

def _normalize(listing: dict, source_id: str) -> RawListing | None:
    """Convert a raw Relay listing dict to a RawListing."""
    try:
        listing_id = str(listing.get("id") or "")
        if not listing_id:
            return None

        title = (listing.get("marketplace_listing_title") or "").strip()
        if not title:
            return None

        # Price: prefer formatted_amount parsing, fall back to amount field
        price_node = listing.get("listing_price") or {}
        amount_raw = price_node.get("amount") or price_node.get("formatted_amount") or ""
        price = _parse_price(amount_raw)

        # Original price (strikethrough) — stored in raw_payload only
        strikethrough_node = listing.get("strikethrough_price") or {}
        original_price_raw = strikethrough_node.get("amount") or ""

        # Image
        photo_node = listing.get("primary_listing_photo") or {}
        image_uri = _safe_get(photo_node, "image", "uri") or ""
        image_urls = [image_uri] if image_uri and image_uri.startswith("http") else []

        # Location
        location_node = listing.get("location") or {}
        geo_node = location_node.get("reverse_geocode") or {}
        location = geo_node.get("city") or None

        product_url = _ITEM_URL.format(listing_id=listing_id)

        return RawListing(
            source_id=source_id,
            external_id=listing_id,
            url=product_url,
            title=title,
            description=None,
            price=price,
            currency=Currency.THB,
            condition=Condition.USED,  # Facebook Marketplace is always second-hand
            seller=SellerInfo(),       # seller info requires login
            location=location,
            image_urls=image_urls,
            posted_at=None,
            scraped_at=datetime.now(timezone.utc),
            raw_payload={
                "listing_id": listing_id,
                "original_price": original_price_raw or None,
            },
        )
    except Exception as exc:
        log.debug("facebook.normalize_error", error=str(exc))
        return None


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

def _parse_price(raw: str | None) -> Decimal:
    """Parse a Thai Baht price string like '฿1,700' or '1700.00' → Decimal."""
    if not raw:
        return Decimal("0")
    cleaned = re.sub(r"[^\d.]", "", str(raw))
    # Remove a trailing lone dot (formatting artifact)
    cleaned = cleaned.rstrip(".")
    try:
        return Decimal(cleaned) if cleaned else Decimal("0")
    except InvalidOperation:
        return Decimal("0")


def _safe_get(obj, *keys):
    """Traverse nested dict/list safely; return None on any missing key."""
    node = obj
    for key in keys:
        if node is None:
            return None
        try:
            node = node[key]
        except (KeyError, IndexError, TypeError):
            return None
    return node


def _url_encode(text: str) -> str:
    """Percent-encode a search keyword for use in a URL query string."""
    return urllib.parse.quote(text, safe="")
