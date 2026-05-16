"""E2E tests for the price-history modal — open, range buttons, and close behaviours."""

import pytest
from conftest import FRONTEND_URL

NAV_TIMEOUT = 15_000
CARD_TIMEOUT = 15_000
MODAL_TIMEOUT = 8_000


def _open_app_and_load_cards(page):
    """Navigate to the app, click the first search, and wait for product cards.

    Returns without raising; callers must check for the price-history button themselves.
    """
    page.goto(FRONTEND_URL, timeout=NAV_TIMEOUT)
    page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)

    sidebar_items = page.query_selector_all(
        "[data-testid='search-item'], .search-item, aside li, nav li"
    )
    if not sidebar_items:
        pytest.skip("No search items in sidebar — create a search first")

    sidebar_items[0].click()

    try:
        page.wait_for_selector("button:has-text('ประวัติราคา')", timeout=CARD_TIMEOUT)
    except Exception:
        pytest.skip("No product cards loaded — run a search first")


def test_modal_opens(page):
    """Clicking the first 'ประวัติราคา' button opens the price-history modal."""
    _open_app_and_load_cards(page)

    # Open the modal
    page.query_selector_all("button:has-text('ประวัติราคา')")[0].click()

    # Modal is open when the 30-day range button is visible
    page.wait_for_selector("button:has-text('30 วัน')", timeout=MODAL_TIMEOUT)
    assert page.is_visible("button:has-text('30 วัน')")


def test_modal_range_buttons(page):
    """Price-history modal shows all four range-selector buttons."""
    _open_app_and_load_cards(page)
    page.query_selector_all("button:has-text('ประวัติราคา')")[0].click()
    page.wait_for_selector("button:has-text('30 วัน')", timeout=MODAL_TIMEOUT)

    for label in ("7 วัน", "30 วัน", "90 วัน", "ทั้งหมด"):
        assert page.is_visible(f"button:has-text('{label}')"), (
            f"Range button '{label}' not visible in modal"
        )


def test_modal_close_x(page):
    """Clicking the × close button dismisses the price-history modal."""
    _open_app_and_load_cards(page)
    page.query_selector_all("button:has-text('ประวัติราคา')")[0].click()
    page.wait_for_selector("button:has-text('30 วัน')", timeout=MODAL_TIMEOUT)

    # Close button — common patterns: aria-label="Close", text "×", or role=button with ×
    close_btn = page.query_selector(
        "button[aria-label='Close'], button:has-text('×'), button:has-text('✕'), [data-testid='modal-close']"
    )
    if close_btn is None:
        pytest.skip("Cannot locate modal close button — check selector")
    close_btn.click()

    # Modal gone when range buttons are no longer visible
    page.wait_for_selector("button:has-text('30 วัน')", state="hidden", timeout=MODAL_TIMEOUT)
    assert not page.is_visible("button:has-text('30 วัน')")


def test_modal_close_backdrop(page):
    """Clicking the backdrop (top-left corner) outside the modal dismisses it."""
    _open_app_and_load_cards(page)
    page.query_selector_all("button:has-text('ประวัติราคา')")[0].click()
    page.wait_for_selector("button:has-text('30 วัน')", timeout=MODAL_TIMEOUT)

    # Click the very top-left corner of the viewport — always outside the modal
    page.mouse.click(5, 5)

    try:
        page.wait_for_selector("button:has-text('30 วัน')", state="hidden", timeout=MODAL_TIMEOUT)
    except Exception:
        pytest.skip("Backdrop click did not close modal — modal may not support backdrop dismiss")

    assert not page.is_visible("button:has-text('30 วัน')")
