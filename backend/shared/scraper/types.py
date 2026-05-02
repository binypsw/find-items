from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional
from pydantic import BaseModel, HttpUrl


class Condition(str, Enum):
    NEW = "new"
    USED = "used"
    REFURBISHED = "refurbished"
    UNKNOWN = "unknown"


class Currency(str, Enum):
    THB = "THB"
    USD = "USD"
    CNY = "CNY"


class StructuredQuery(BaseModel):
    """Output of LLM query parser (Gemini / Typhoon / regex)."""

    raw_query: str = ""          # original user input — available to all plugins
    keywords: list[str]
    keywords_th: list[str] = []
    keywords_en: list[str] = []
    category: Optional[str] = None
    condition: Condition = Condition.UNKNOWN
    min_price_thb: Optional[Decimal] = None
    max_price_thb: Optional[Decimal] = None
    location: Optional[str] = None
    exclude_keywords: list[str] = []
    source_filter: list[str] = []
    extra_criteria: dict = {}


class SellerInfo(BaseModel):
    name: Optional[str] = None
    rating: Optional[float] = None
    review_count: Optional[int] = None
    sold_count: Optional[int] = None
    is_verified: bool = False


class RawListing(BaseModel):
    """Output of a plugin scraper — before DB normalization."""

    source_id: str
    external_id: str
    url: str
    title: str
    description: Optional[str] = None
    price: Decimal
    currency: Currency
    condition: Condition = Condition.UNKNOWN
    seller: SellerInfo = SellerInfo()
    location: Optional[str] = None
    image_urls: list[str] = []
    posted_at: Optional[datetime] = None
    scraped_at: datetime
    raw_payload: dict = {}
