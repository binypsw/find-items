"""Smoke tests — one request per endpoint, verify status code and top-level shape only."""

import pytest
import httpx
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from conftest import API_BASE


def _first_listing_id(client: httpx.Client) -> int | None:
    """Return the id of the first active listing, or None if DB is empty."""
    r = client.get(f"{API_BASE}/api/listings", params={"page_size": 1, "status": "active"})
    data = r.json()
    items = data.get("items", [])
    if not items:
        return None
    return items[0]["id"]


def _first_search_id(client: httpx.Client) -> int | None:
    """Return the id of the first saved search, or None."""
    r = client.get(f"{API_BASE}/api/searches")
    searches = r.json()
    if not searches:
        return None
    return searches[0]["id"]


def test_searches_list():
    """GET /api/searches returns 200 and a JSON list."""
    with httpx.Client() as client:
        r = client.get(f"{API_BASE}/api/searches")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_sources_list():
    """GET /api/sources returns 200, list, and each item has id + enabled fields."""
    with httpx.Client() as client:
        r = client.get(f"{API_BASE}/api/sources")
    assert r.status_code == 200
    sources = r.json()
    assert isinstance(sources, list)
    if sources:
        first = sources[0]
        assert "id" in first
        assert "enabled" in first


def test_listings_list():
    """GET /api/listings returns 200 with items and total fields."""
    with httpx.Client() as client:
        r = client.get(f"{API_BASE}/api/listings")
    assert r.status_code == 200
    data = r.json()
    assert "items" in data
    assert "total" in data


def test_listings_first_item_schema():
    """GET /api/listings?page_size=1 — first item has id, current_price_thb, source_id."""
    with httpx.Client() as client:
        r = client.get(f"{API_BASE}/api/listings", params={"page_size": 1})
    assert r.status_code == 200
    items = r.json().get("items", [])
    if not items:
        pytest.skip("No listings in DB — run a search first")
    item = items[0]
    assert "id" in item
    assert "current_price_thb" in item
    assert "source_id" in item


def test_price_history_endpoint():
    """GET /api/listings/{id}/price-history returns 200 and a list."""
    with httpx.Client() as client:
        listing_id = _first_listing_id(client)
        if listing_id is None:
            pytest.skip("No listings in DB — run a search first")
        r = client.get(f"{API_BASE}/api/listings/{listing_id}/price-history")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_price_stats_endpoint():
    """GET /api/listings/{id}/price-stats returns 200 with is_likely_fake_sale field."""
    with httpx.Client() as client:
        listing_id = _first_listing_id(client)
        if listing_id is None:
            pytest.skip("No listings in DB — run a search first")
        r = client.get(f"{API_BASE}/api/listings/{listing_id}/price-stats")
    if r.status_code == 404:
        pytest.skip("price-stats endpoint not yet implemented")
    assert r.status_code == 200
    assert "is_likely_fake_sale" in r.json()


def test_dashboard_endpoint():
    """GET /api/dashboard/{search_id}/top?limit=5 returns 200 and a list."""
    with httpx.Client() as client:
        search_id = _first_search_id(client)
        if search_id is None:
            pytest.skip("No searches in DB — create a search first")
        r = client.get(f"{API_BASE}/api/dashboard/{search_id}/top", params={"limit": 5})
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_listing_404():
    """GET /api/listings/9999999 returns 404."""
    with httpx.Client() as client:
        r = client.get(f"{API_BASE}/api/listings/9999999")
    assert r.status_code == 404


def test_alerts_list_ok():
    """GET /api/alerts returns 200 and a JSON list."""
    with httpx.Client() as client:
        r = client.get(f"{API_BASE}/api/alerts")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_notification_config_ok():
    """GET /api/config/notifications returns 200 with discord_webhook_url field."""
    with httpx.Client() as client:
        r = client.get(f"{API_BASE}/api/config/notifications")
    assert r.status_code == 200
    data = r.json()
    assert "discord_webhook_url" in data
