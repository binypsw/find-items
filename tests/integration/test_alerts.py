"""Integration tests for /api/alerts and /api/config/notifications (F1 feature)."""

import pytest
import httpx
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from conftest import API_BASE


def _first_listing_id(client: httpx.Client) -> int | None:
    """Return the id of the first listing, or None if DB is empty."""
    r = client.get(f"{API_BASE}/api/listings", params={"page_size": 1})
    items = r.json().get("items", [])
    if not items:
        return None
    return items[0]["id"]


def test_create_and_delete_alert():
    """POST /api/alerts creates alert with correct fields; DELETE removes it."""
    with httpx.Client() as client:
        # Get a listing id
        r = client.get(f"{API_BASE}/api/listings", params={"page_size": 1})
        assert r.status_code == 200
        items = r.json()["items"]
        if not items:
            pytest.skip("No listings in DB")
        listing_id = items[0]["id"]

        # Create alert
        r = client.post(f"{API_BASE}/api/alerts", json={
            "listing_id": listing_id,
            "target_price": 999999.0,
            "comparison": "lte",
            "notify_channels": ["discord"]
        })
        assert r.status_code == 201, f"Expected 201, got {r.status_code}: {r.text}"
        alert_id = r.json()["id"]
        assert r.json()["is_active"] == True
        assert r.json()["listing_title"] != ""

        # Delete alert
        r = client.delete(f"{API_BASE}/api/alerts/{alert_id}")
        assert r.status_code == 204, f"Expected 204, got {r.status_code}: {r.text}"


def test_notification_config_put():
    """PUT /api/config/notifications sets discord_webhook_url to None."""
    with httpx.Client() as client:
        # Set webhook to None
        r = client.put(f"{API_BASE}/api/config/notifications", json={"discord_webhook_url": None})
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        assert r.json()["discord_webhook_url"] is None


def test_alerts_list_returns_list():
    """GET /api/alerts returns 200 with a list."""
    with httpx.Client() as client:
        r = client.get(f"{API_BASE}/api/alerts")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_alert_patch_toggle():
    """PATCH /api/alerts/{id} can toggle is_active field."""
    with httpx.Client() as client:
        listing_id = _first_listing_id(client)
        if listing_id is None:
            pytest.skip("No listings in DB")

        # Create alert
        r = client.post(f"{API_BASE}/api/alerts", json={
            "listing_id": listing_id,
            "target_price": 500.0,
            "comparison": "lte",
            "notify_channels": ["discord"]
        })
        assert r.status_code == 201
        alert_id = r.json()["id"]
        assert r.json()["is_active"] == True

        # Patch: disable alert
        r = client.patch(f"{API_BASE}/api/alerts/{alert_id}", json={"is_active": False})
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        assert r.json()["is_active"] == False

        # Cleanup
        client.delete(f"{API_BASE}/api/alerts/{alert_id}")
