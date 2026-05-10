from functools import lru_cache
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Database
    database_url: str = "postgresql+asyncpg://finditem:changeme@postgres:5432/finditem"
    postgres_user: str = "finditem"
    postgres_password: str = "changeme"
    postgres_db: str = "finditem"

    # Redis
    redis_url: str = "redis://redis:6379/0"
    celery_broker_url: str = "redis://redis:6379/1"
    celery_result_backend: str = "redis://redis:6379/2"

    # Browserless
    browserless_url: str = "ws://browserless:3000"
    browserless_token: str = "changeme"

    # LLM — Tier 1: Gemini (primary, free 1500/day)
    google_api_key: Optional[str] = None
    gemini_model: str = "gemini-2.0-flash"

    # LLM — Tier 2: Typhoon (fallback, free, Thai-specialized)
    typhoon_api_key: Optional[str] = None
    typhoon_base_url: str = "https://api.opentyphoon.ai/v1"
    typhoon_model: str = "typhoon-v2-70b-instruct"

    # Scraping API providers
    scrapfly_api_key: Optional[str] = None
    zenrows_api_key: Optional[str] = None
    apify_api_token: Optional[str] = None
    scraping_api_monthly_budget: int = 180000
    adaptive_tiering_enabled: bool = True
    fb_marketplace_daily_runs: int = 3
    default_poll_interval_minutes: int = 720

    # Proxy (optional)
    proxy_pool_urls: str = ""
    shopee_proxy_url: Optional[str] = None

    # Discord
    discord_webhook_url: Optional[str] = None

    # Security
    fernet_key: Optional[str] = None
    session_secret: str = "changeme"

    # Misc
    tz: str = "Asia/Bangkok"
    log_level: str = "INFO"

    @property
    def proxy_list(self) -> list[str]:
        if not self.proxy_pool_urls:
            return []
        return [p.strip() for p in self.proxy_pool_urls.split(",") if p.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
