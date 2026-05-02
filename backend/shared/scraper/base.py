from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, AsyncIterator, Literal, Optional
from pydantic import BaseModel

from shared.scraper.types import RawListing, StructuredQuery

if TYPE_CHECKING:
    pass

ScraperTier = Literal["direct", "browserless", "managed_api"]


class ScraperConfig(BaseModel):
    tier: ScraperTier
    rate_limit_rps: float = 0.5
    use_proxy: bool = False
    api_provider: Optional[Literal["scrapfly", "zenrows", "apify"]] = None
    retry_max_attempts: int = 5
    requires_session: bool = False
    cookies_source_id: Optional[str] = None


class AbstractScraper(ABC):
    source_id: str        # class-level attribute, e.g. "shopee"
    display_name: str     # e.g. "Shopee Thailand"
    base_url: str
    config: ScraperConfig

    def __init__(self, deps: "ScraperDependencies"):
        self.deps = deps

    @abstractmethod
    async def search(self, query: StructuredQuery, limit: int = 50) -> AsyncIterator[RawListing]:
        """Yield RawListing one at a time — avoid loading all into memory."""
        ...

    @abstractmethod
    async def get_detail(self, url: str) -> RawListing:
        """Fetch a single listing by URL (used when user pastes a URL)."""
        ...

    async def health_check(self) -> bool:
        """Default: HTTP HEAD at base_url."""
        try:
            async with self.deps.http_client as client:
                r = await client.head(self.base_url, timeout=10)
                return r.status_code < 500
        except Exception:
            return False

    def normalize_keywords(self, query: StructuredQuery) -> str:
        """Convert StructuredQuery to a single search string for the source.

        Strategy (Thai-first, no duplication):
        1. If raw_query is set, use it directly — it's exactly what the user typed
           and is already a well-formed Thai/English mixed query.
        2. Fallback: join keywords_th (avoids repeating both Thai + English variants).
        3. Fallback: join keywords_en.
        4. Fallback: join all keywords.

        Subclasses may override for source-specific syntax (e.g. strip condition words,
        add category prefix, etc.).
        """
        if query.raw_query:
            return query.raw_query.strip()
        if query.keywords_th:
            return " ".join(query.keywords_th).strip()
        if query.keywords_en:
            return " ".join(query.keywords_en).strip()
        return " ".join(query.keywords).strip()


class ScraperDependencies:
    """Dependency container injected into every scraper plugin."""

    def __init__(
        self,
        http_client=None,
        browserless=None,
        scraping_api=None,
        proxy_mgr=None,
        cookie_store=None,
        db_session=None,
        logger=None,
    ):
        self.http_client = http_client
        self.browserless = browserless
        self.scraping_api = scraping_api
        self.proxy_mgr = proxy_mgr
        self.cookie_store = cookie_store
        self.db_session = db_session
        self.logger = logger
