import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from shared.config import get_settings
from shared.core.browserless_client import BrowserlessClient
from shared.core.proxy_manager import ProxyManager
from shared.core.pubsub import RedisPubSub
from shared.scraper.base import AbstractScraper, ScraperDependencies
from shared.scraper.plugins import get_all_plugins, get_plugin

log = structlog.get_logger()
settings = get_settings()

_proxy_manager = ProxyManager()
_browserless = BrowserlessClient()
_pubsub = RedisPubSub()


def build_deps(db: AsyncSession, source_id: str) -> ScraperDependencies:
    """Build ScraperDependencies for the given source_id."""
    from shared.core.scraping_api.zenrows import ZenRowsClient
    from shared.core.cookie_store import CookieStore

    scraping_api = ZenRowsClient() if settings.zenrows_api_key else None

    cookie_store = None
    if settings.fernet_key:
        try:
            cookie_store = CookieStore(db)
        except ValueError:
            pass

    return ScraperDependencies(
        http_client=None,  # curl_cffi session created per-request inside plugins
        browserless=_browserless,
        scraping_api=scraping_api,
        proxy_mgr=_proxy_manager,
        cookie_store=cookie_store,
        db_session=db,
        logger=log.bind(source_id=source_id),
    )


def get_scraper(source_id: str, db: AsyncSession) -> AbstractScraper | None:
    """Instantiate and return a scraper for source_id, or None if not found."""
    plugin_cls = get_plugin(source_id)
    if not plugin_cls:
        log.warning("scraper.plugin_not_found", source_id=source_id)
        return None
    deps = build_deps(db, source_id)
    return plugin_cls(deps)


def list_available_sources() -> list[str]:
    return list(get_all_plugins().keys())
