"""Integration tests for /api/dashboard — ranked listing shape and scoring logic."""

import pytest
import httpx
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from conftest import API_BASE


def _first_search_id(client: httpx.Client) -> int | None:
    """Return the id of the first saved search, or None."""
    r = client.get(f"{API_BASE}/api/searches")
    searches = r.json()
    if not searches:
        return None
    return searches[0]["id"]


def _require_search_with_results(client: httpx.Client) -> tuple[int, list]:
    """Return (search_id, ranked_items) for the first search that has dashboard results."""
    r = client.get(f"{API_BASE}/api/searches")
    searches = r.json()
    if not searches:
        pytest.skip("No searches in DB — create a search first")

    for search in searches:
        sid = search["id"]
        top = client.get(f"{API_BASE}/api/dashboard/{sid}/top", params={"limit": 50})
        items = top.json()
        if items:
            return sid, items

    pytest.skip("No dashboard results found — run at least one search first")


def test_dashboard_ranked_fields():
    """Each ranked listing contains score (float), rank (int), and price_change_7d_pct (float or null)."""
    with httpx.Client() as client:
        _, items = _require_search_with_results(client)

    for item in items:
        assert "score" in item, f"Missing 'score' in item id={item.get('id')}"
        assert "rank" in item, f"Missing 'rank' in item id={item.get('id')}"
        assert "price_change_7d_pct" in item, f"Missing 'price_change_7d_pct' in item id={item.get('id')}"
        assert isinstance(item["score"], (int, float)), "score must be numeric"
        assert isinstance(item["rank"], int), "rank must be an integer"
        pct = item["price_change_7d_pct"]
        assert pct is None or isinstance(pct, (int, float)), "price_change_7d_pct must be float or null"


def test_dashboard_rank_sequential():
    """rank values start at 1 and are sequential with no gaps."""
    with httpx.Client() as client:
        _, items = _require_search_with_results(client)

    ranks = [item["rank"] for item in items]
    expected = list(range(1, len(ranks) + 1))
    assert ranks == expected, f"Ranks are not sequential: {ranks}"


def test_dashboard_scores_positive():
    """All ranking scores must be greater than zero."""
    with httpx.Client() as client:
        _, items = _require_search_with_results(client)

    for item in items:
        assert item["score"] > 0, f"Item id={item.get('id')} has non-positive score: {item['score']}"


def test_dashboard_empty_returns_list():
    """GET /api/dashboard/9999999/top returns 200 with an empty list — not a 404."""
    with httpx.Client() as client:
        r = client.get(f"{API_BASE}/api/dashboard/9999999/top")
    assert r.status_code == 200
    assert r.json() == [], f"Expected empty list, got: {r.json()}"
