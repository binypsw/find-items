"""Integration tests for /api/listings — detailed field and behaviour checks."""

import pytest
import httpx
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from conftest import API_BASE

VALID_TREND_VALUES = {"up", "down", "stable", None}


def _first_listing_id(client: httpx.Client) -> int | None:
    """Return the id of the first active listing, or None if DB is empty."""
    r = client.get(f"{API_BASE}/api/listings", params={"page_size": 1, "status": "active"})
    items = r.json().get("items", [])
    if not items:
        return None
    return items[0]["id"]


def _require_listing_id(client: httpx.Client) -> int:
    """Return a listing id or skip the test if none exist."""
    lid = _first_listing_id(client)
    if lid is None:
        pytest.skip("No listings in DB — run a search first")
    return lid


def test_price_stats_all_fields():
    """price-stats response contains every required analytics field."""
    with httpx.Client() as client:
        lid = _require_listing_id(client)
        r = client.get(f"{API_BASE}/api/listings/{lid}/price-stats")
    if r.status_code == 404:
        pytest.skip("price-stats endpoint not yet implemented")
    assert r.status_code == 200
    data = r.json()
    required = [
        "listing_id",
        "snapshots_count",
        "period_days",
        "price_current",
        "price_min",
        "price_max",
        "price_avg",
        "trend_7d",
        "trend_7d_pct",
        "is_likely_fake_sale",
        "fake_sale_reason",
    ]
    for field in required:
        assert field in data, f"Missing field: {field}"


def test_price_stats_trend_valid_values():
    """trend_7d value must be 'up', 'down', 'stable', or null — nothing else."""
    with httpx.Client() as client:
        lid = _require_listing_id(client)
        r = client.get(f"{API_BASE}/api/listings/{lid}/price-stats")
    if r.status_code == 404:
        pytest.skip("price-stats endpoint not yet implemented")
    assert r.status_code == 200
    trend = r.json().get("trend_7d")
    assert trend in VALID_TREND_VALUES, f"Unexpected trend_7d value: {trend!r}"


def test_price_history_all_ranges():
    """price-history endpoint accepts 7d, 30d, 90d, and all range parameters."""
    with httpx.Client() as client:
        lid = _require_listing_id(client)
        for rng in ("7d", "30d", "90d", "all"):
            r = client.get(
                f"{API_BASE}/api/listings/{lid}/price-history",
                params={"range": rng},
            )
            assert r.status_code == 200, f"range={rng} returned {r.status_code}"
            assert isinstance(r.json(), list), f"range={rng} did not return a list"


def test_price_history_invalid_range():
    """price-history with an unknown range value returns 422 validation error."""
    with httpx.Client() as client:
        lid = _require_listing_id(client)
        r = client.get(
            f"{API_BASE}/api/listings/{lid}/price-history",
            params={"range": "invalid"},
        )
    assert r.status_code == 422


def test_listings_pagination():
    """Two consecutive pages of 5 both return 200 (skip order check when <6 items)."""
    with httpx.Client() as client:
        r_total = client.get(f"{API_BASE}/api/listings", params={"page_size": 1})
    total = r_total.json().get("total", 0)
    if total == 0:
        pytest.skip("No listings in DB — run a search first")

    with httpx.Client() as client:
        r1 = client.get(f"{API_BASE}/api/listings", params={"page": 1, "page_size": 5})
        r2 = client.get(f"{API_BASE}/api/listings", params={"page": 2, "page_size": 5})

    assert r1.status_code == 200
    assert r2.status_code == 200

    # Only check that pages differ when we actually have enough items
    if total >= 6:
        ids_page1 = {item["id"] for item in r1.json()["items"]}
        ids_page2 = {item["id"] for item in r2.json()["items"]}
        assert ids_page1.isdisjoint(ids_page2), "Page 1 and page 2 share listing ids"


def test_listing_not_found():
    """GET /api/listings/9999999 returns 404 with a detail field in the response body."""
    with httpx.Client() as client:
        r = client.get(f"{API_BASE}/api/listings/9999999")
    assert r.status_code == 404
    data = r.json()
    assert "detail" in data, "404 response body must contain a detail field"
