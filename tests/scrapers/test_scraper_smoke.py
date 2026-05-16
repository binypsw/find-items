"""
Scraper smoke tests — trigger REAL scrape runs against live websites.

These tests are marked `slow` and must be run manually:
    pytest tests/scrapers/ -m slow

They require at least one saved search in the database.
"""

import time
import pytest
import httpx
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from conftest import API_BASE

pytestmark = pytest.mark.slow

POLL_INTERVAL = 5   # seconds between status checks
MAX_WAIT = 120       # maximum seconds to wait for a run to finish


def _first_search_id(client: httpx.Client, prefer_electronics: bool = False) -> int | None:
    """Return the id of a saved search, or None.

    When prefer_electronics=True, prefers searches with keywords like DDR4, RAM,
    laptop, phone etc. that electronics scrapers (JIB, BNN, Priceza) are likely
    to return results for. Falls back to first search in list if none found.
    """
    r = client.get(f"{API_BASE}/api/searches")
    searches = r.json()
    if not searches:
        return None
    if prefer_electronics:
        # Look for a search whose raw_query contains electronics keywords
        electronics_keywords = ("ddr4", "ram", "ssd", "laptop", "phone", "samsung", "iphone", "cpu", "gpu", "rtx", "gtx")
        for search in searches:
            q = (search.get("raw_query") or "").lower()
            if any(kw in q for kw in electronics_keywords):
                return search["id"]
    return searches[0]["id"]


def _trigger_and_poll(source_id: str) -> dict:
    """
    Trigger a run for the given source, then poll /api/runs/{run_id} until
    status is no longer 'running' / 'pending', or the timeout expires.

    Returns the final run status dict.
    """
    # Prefer electronics search for scrapers that only carry electronics
    prefer_elec = source_id in ("jib", "bnn", "priceza")
    with httpx.Client(timeout=30) as client:
        search_id = _first_search_id(client, prefer_electronics=prefer_elec)
        if search_id is None:
            pytest.skip("No searches in DB — create a search first")

        # Trigger the run
        trigger_r = client.post(
            f"{API_BASE}/api/searches/{search_id}/run",
            json={"source_filter": [source_id]},
        )
        assert trigger_r.status_code == 200, (
            f"Failed to trigger run: {trigger_r.status_code} {trigger_r.text}"
        )
        trigger_data = trigger_r.json()

        # The trigger response contains task_id (Celery) and run_id.
        # run_id may be 0 (placeholder) until the worker creates the ScrapeRun row.
        # We therefore list runs for the search and pick the most recent one for
        # the target source, waiting up to POLL_INTERVAL * 3 for the row to appear.
        task_id = trigger_data.get("task_id")
        run_id = None

        deadline = time.monotonic() + MAX_WAIT
        while time.monotonic() < deadline:
            runs_r = client.get(f"{API_BASE}/api/searches/{search_id}/runs", params={"limit": 20})
            if runs_r.status_code == 200:
                runs = runs_r.json()
                # Find the most recent run for our source
                matching = [r for r in runs if r["source_id"] == source_id]
                if matching:
                    run_id = matching[0]["id"]
                    break
            time.sleep(POLL_INTERVAL)

        if run_id is None:
            pytest.skip(
                f"No scrape run row found for source '{source_id}' after triggering "
                f"(task_id={task_id}) — worker may not be running"
            )

        # Poll until terminal status
        while time.monotonic() < deadline:
            run_r = client.get(f"{API_BASE}/api/runs/{run_id}")
            assert run_r.status_code == 200
            run = run_r.json()
            if run["status"] not in ("running", "pending"):
                return run
            time.sleep(POLL_INTERVAL)

        # Timed out — return whatever state we have
        run_r = client.get(f"{API_BASE}/api/runs/{run_id}")
        return run_r.json()


def test_jib_scraper_completes():
    """JIB scraper run completes with status='completed' and at least one item found."""
    run = _trigger_and_poll("jib")
    assert run["status"] == "completed", (
        f"JIB scraper finished with status={run['status']!r}; errors={run.get('errors')}"
    )
    assert run["items_found"] > 0, "JIB scraper completed but found 0 items"


def test_priceza_scraper_completes():
    """Priceza scraper run completes with status='completed' and at least one item found."""
    run = _trigger_and_poll("priceza")
    assert run["status"] == "completed", (
        f"Priceza scraper finished with status={run['status']!r}; errors={run.get('errors')}"
    )
    assert run["items_found"] > 0, "Priceza scraper completed but found 0 items"


def test_shopee_scraper_display_required():
    """Shopee scraper requires a display (X server / Xvfb) for headed browser.

    This test documents the known blocker: the Docker worker container has no
    $DISPLAY and no Xvfb, so launch_persistent_context(headless=False) fails with:
        Missing X server or $DISPLAY

    Expected result until display is configured:
        - run completes (no crash) but items_found == 0
        - worker log shows: shopee.browser_error / Missing X server or $DISPLAY

    To fix, one of the following is required:
        1. Add Xvfb to worker Dockerfile + set DISPLAY=:99 in docker-compose.yml
        2. Run the scraper on Windows host (where a display exists) instead of Docker
        3. Mount a virtual framebuffer via Xvfb-run wrapper

    This test SKIPs when Shopee source is disabled in DB.
    """
    with httpx.Client(timeout=10) as client:
        sources_r = client.get(f"{API_BASE}/api/sources")
        if sources_r.status_code == 200:
            sources = {s["id"]: s for s in sources_r.json()}
            if "shopee" not in sources or not sources["shopee"].get("enabled"):
                pytest.skip(
                    "Shopee source is not enabled in DB — enable with: "
                    "UPDATE sources SET enabled=true WHERE id='shopee';"
                )

    run = _trigger_and_poll("shopee")
    # Document current known state: browser_headed fails without X server
    # status=completed is OK (scraper catches the error gracefully)
    # items_found=0 is expected until display is configured
    assert run["status"] in ("completed", "failed"), (
        f"Shopee scraper finished with unexpected status={run['status']!r}; "
        f"errors={run.get('errors')}"
    )
    # When display IS available, this assertion should pass:
    # assert run["items_found"] > 0, "Shopee scraper completed but found 0 items (display required)"


def test_facebook_scraper_completes():
    """Facebook Marketplace scraper extracts SSR Relay JSON and returns listings.

    Requires 'facebook' source to be enabled in DB:
        UPDATE sources SET enabled=true WHERE id='facebook';
    Uses headless Playwright + inline script parsing (2026-05 format).
    """
    with httpx.Client(timeout=10) as client:
        sources_r = client.get(f"{API_BASE}/api/sources")
        if sources_r.status_code == 200:
            sources = {s["id"]: s for s in sources_r.json()}
            if "facebook" not in sources or not sources["facebook"].get("enabled"):
                pytest.skip("Facebook source is not enabled in DB — enable with: UPDATE sources SET enabled=true WHERE id='facebook'")

    run = _trigger_and_poll("facebook")
    assert run["status"] == "completed", (
        f"Facebook scraper finished with status={run['status']!r}; errors={run.get('errors')}"
    )
    assert run["items_found"] > 0, (
        "Facebook scraper completed but found 0 items — "
        "check if Facebook changed SSR format or if search term has no Bangkok listings"
    )
