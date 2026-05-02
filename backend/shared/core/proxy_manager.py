import itertools
from typing import Optional

import structlog

from shared.config import get_settings

log = structlog.get_logger()


class ProxyManager:
    """Round-robin proxy rotation for tier=direct scraping.

    Configure PROXY_POOL_URLS in .env as comma-separated proxy URLs:
    http://user:pass@proxy1:port,http://user:pass@proxy2:port
    """

    def __init__(self, proxy_urls: list[str] | None = None):
        settings = get_settings()
        urls = proxy_urls if proxy_urls is not None else settings.proxy_list
        self._pool = list(urls)
        self._cycle = itertools.cycle(self._pool) if self._pool else None

    @property
    def has_proxies(self) -> bool:
        return bool(self._pool)

    def next(self) -> Optional[str]:
        """Return the next proxy URL, or None if pool is empty."""
        if not self._cycle:
            return None
        return next(self._cycle)

    def get_proxies_dict(self) -> Optional[dict[str, str]]:
        """Return requests-style proxy dict, or None."""
        url = self.next()
        if not url:
            return None
        return {"http": url, "https": url}
