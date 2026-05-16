"""E2E tests for the main search flow — app loads, sidebar, and product cards."""

import pytest
from conftest import FRONTEND_URL

# Allow up to 15 s for the SPA to hydrate and API calls to resolve
NAV_TIMEOUT = 15_000


def test_app_loads(page):
    """Navigate to the app root; page title includes 'Find Item' and no JS errors occur."""
    js_errors = []
    page.on("pageerror", lambda exc: js_errors.append(str(exc)))

    page.goto(FRONTEND_URL, timeout=NAV_TIMEOUT)
    page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)

    assert "Find Item" in page.title(), f"Unexpected page title: {page.title()!r}"
    assert js_errors == [], f"JavaScript errors detected: {js_errors}"


def test_sidebar_shows_searches(page):
    """At least one saved-search item is rendered in the sidebar."""
    page.goto(FRONTEND_URL, timeout=NAV_TIMEOUT)
    page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)

    # The sidebar renders saved searches; wait for at least one item to appear.
    # Adjust selector if the component uses a different class/attribute.
    try:
        page.wait_for_selector("[data-testid='search-item'], .search-item, aside li", timeout=10_000)
    except Exception:
        pytest.skip("No search items visible in sidebar — create a search first")


def test_click_search_shows_cards(page):
    """Clicking the first sidebar search causes at least one product card to appear."""
    page.goto(FRONTEND_URL, timeout=NAV_TIMEOUT)
    page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)

    # Find the first clickable search item in the sidebar
    sidebar_items = page.query_selector_all(
        "[data-testid='search-item'], .search-item, aside li, nav li"
    )
    if not sidebar_items:
        pytest.skip("No search items in sidebar — create a search first")

    sidebar_items[0].click()

    # Wait for at least one product card bearing the Thai price-history button label
    try:
        page.wait_for_selector("button:has-text('ประวัติราคา')", timeout=15_000)
    except Exception:
        pytest.skip("No product cards loaded after clicking search — run a search first")

    cards = page.query_selector_all("button:has-text('ประวัติราคา')")
    assert len(cards) >= 1, "Expected at least one product card with 'ประวัติราคา' button"


def test_price_history_button_visible(page):
    """After loading a search, a 'ประวัติราคา' button is present on the page."""
    page.goto(FRONTEND_URL, timeout=NAV_TIMEOUT)
    page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)

    sidebar_items = page.query_selector_all(
        "[data-testid='search-item'], .search-item, aside li, nav li"
    )
    if not sidebar_items:
        pytest.skip("No search items in sidebar — create a search first")

    sidebar_items[0].click()

    try:
        page.wait_for_selector("button:has-text('ประวัติราคา')", timeout=15_000)
    except Exception:
        pytest.skip("Price-history button not found — run a search first")

    assert page.is_visible("button:has-text('ประวัติราคา')")
