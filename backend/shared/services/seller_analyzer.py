"""Seller signal extraction and risk classification for F3.

Reads from listing.seller_payload (normalized SellerInfo dict stored by scrapers)
and produces structured seller signals + a risk warning level.

No DB writes — pure data transformation, safe to call from API handlers.
"""
from typing import Optional
from pydantic import BaseModel


class SellerSignals(BaseModel):
    """Extracted & normalized seller signals from listing.seller_payload."""

    name: Optional[str] = None
    rating: Optional[float] = None          # 0.0 – 5.0
    review_count: Optional[int] = None
    sold_count: Optional[int] = None
    is_verified: bool = False
    response_rate: Optional[float] = None   # 0.0 – 100.0 (%)
    shop_age_days: Optional[int] = None


class SellerRisk(BaseModel):
    """Output of the seller warning classifier."""

    warning_level: str   # "ok" | "caution" | "warning"
    reasons: list[str]
    signals: SellerSignals


# ---- Thresholds (tune as needed) ----------------------------------------

_RATING_WARN_THRESHOLD = 3.5          # below this → caution/warning
_RATING_OK_THRESHOLD = 4.0            # at or above → no penalty
_REVIEW_WARN_THRESHOLD = 5            # fewer reviews → caution
_SOLD_WARN_THRESHOLD = 5              # sold < N → caution signal
_RESPONSE_RATE_WARN = 70.0            # % response rate below this


def extract_seller_signals(seller_payload: dict) -> SellerSignals:
    """Parse seller_payload (stored as JSONB in listings table) into SellerSignals.

    seller_payload is the JSON-serialized SellerInfo pydantic model written by
    scrape_task.py via `raw.seller.model_dump()`.  Fields present depend on source:

    - lazada:  name, rating (0-5), review_count, sold_count
    - kaidee:  name, rating (0-5)
    - shopee:  sold_count
    - facebook: (empty — login required)
    - jib/bnn/priceza: usually empty (retail stores)
    """
    if not seller_payload or not isinstance(seller_payload, dict):
        return SellerSignals()

    def _safe_float(val) -> Optional[float]:
        try:
            f = float(val)
            return f if f >= 0 else None
        except (TypeError, ValueError):
            return None

    def _safe_int(val) -> Optional[int]:
        try:
            i = int(val)
            return i if i >= 0 else None
        except (TypeError, ValueError):
            return None

    rating_raw = seller_payload.get("rating")
    rating = _safe_float(rating_raw)
    # Some sources store rating out of 100 — normalise to 5.0 scale
    if rating is not None and rating > 5.0:
        if rating <= 100.0:
            rating = round(rating / 20.0, 2)  # e.g. 92 → 4.60
        else:
            rating = None  # garbage value

    return SellerSignals(
        name=seller_payload.get("name") or None,
        rating=rating,
        review_count=_safe_int(seller_payload.get("review_count")),
        sold_count=_safe_int(seller_payload.get("sold_count")),
        is_verified=bool(seller_payload.get("is_verified", False)),
        response_rate=_safe_float(seller_payload.get("response_rate")),
        shop_age_days=_safe_int(seller_payload.get("shop_age_days")),
    )


def classify_seller_risk(signals: SellerSignals) -> SellerRisk:
    """Score seller risk and assign a warning level.

    Rules (accumulative — multiple hits raise the level):
      warning  :  rating < 3.0  OR  (rating < _RATING_WARN_THRESHOLD AND review_count >= 10)
      caution  :  rating 3.0-3.4  OR  review_count < _REVIEW_WARN_THRESHOLD (and rating known)
                  OR sold_count < _SOLD_WARN_THRESHOLD (and sold_count known)
                  OR response_rate < _RESPONSE_RATE_WARN
      ok       :  default when no bad signals
    """
    reasons: list[str] = []
    bad_score = 0  # accumulate severity points

    # Rating checks
    if signals.rating is not None:
        if signals.rating < 3.0:
            reasons.append(f"Low rating: {signals.rating:.1f}/5")
            bad_score += 2
        elif signals.rating < _RATING_WARN_THRESHOLD:
            reasons.append(f"Below-average rating: {signals.rating:.1f}/5")
            bad_score += 1

    # Review count checks (only meaningful if we also have rating)
    if signals.review_count is not None:
        if signals.review_count == 0:
            reasons.append("No reviews")
            bad_score += 1
        elif signals.review_count < _REVIEW_WARN_THRESHOLD:
            reasons.append(f"Very few reviews: {signals.review_count}")
            bad_score += 1

    # Sold count
    if signals.sold_count is not None and signals.sold_count < _SOLD_WARN_THRESHOLD:
        reasons.append(f"Very few sales: {signals.sold_count}")
        bad_score += 1

    # Response rate
    if signals.response_rate is not None and signals.response_rate < _RESPONSE_RATE_WARN:
        reasons.append(f"Low response rate: {signals.response_rate:.0f}%")
        bad_score += 1

    # Not verified (minor signal — only adds context, no score increase)
    if not signals.is_verified and (signals.rating is not None or signals.review_count is not None):
        reasons.append("Seller not verified")
        # intentionally no bad_score increase — informational only

    # Determine level
    if bad_score >= 2:
        warning_level = "warning"
    elif bad_score == 1:
        warning_level = "caution"
    else:
        warning_level = "ok"

    return SellerRisk(
        warning_level=warning_level,
        reasons=reasons,
        signals=signals,
    )
