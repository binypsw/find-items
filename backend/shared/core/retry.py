import structlog
from tenacity import (
    RetryCallState,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

log = structlog.get_logger()


def _log_retry(retry_state: RetryCallState) -> None:
    log.warning(
        "http.retry",
        attempt=retry_state.attempt_number,
        wait=retry_state.next_action.sleep if retry_state.next_action else None,
        exc=str(retry_state.outcome.exception()) if retry_state.outcome else None,
    )


def scraper_retry(max_attempts: int = 5):
    """Decorator factory for scraping HTTP calls.

    Retries on connection errors and HTTP 429/503.
    Permanent 404/410 must be caught by the caller and NOT retried.
    """
    from curl_cffi.requests.exceptions import RequestsError

    return retry(
        retry=retry_if_exception_type((RequestsError, TimeoutError, ConnectionError)),
        wait=wait_exponential_jitter(initial=2, max=60),
        stop=stop_after_attempt(max_attempts),
        before_sleep=_log_retry,
        reraise=True,
    )


def webhook_retry(max_attempts: int = 3):
    """Retry for Discord webhook / internal API calls (uses httpx)."""
    import httpx

    return retry(
        retry=retry_if_exception_type((httpx.TransportError, httpx.TimeoutException)),
        wait=wait_exponential_jitter(initial=1, max=30),
        stop=stop_after_attempt(max_attempts),
        before_sleep=_log_retry,
        reraise=True,
    )
