import pytest
from playwright.sync_api import sync_playwright

FRONTEND_URL = "http://localhost:3001"


@pytest.fixture(scope="session")
def browser():
    """Launch a single Chromium browser instance shared across the entire test session."""
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        yield b
        b.close()


@pytest.fixture
def page(browser):
    """Create a fresh browser page for each test and close it afterwards."""
    p = browser.new_page()
    yield p
    p.close()
