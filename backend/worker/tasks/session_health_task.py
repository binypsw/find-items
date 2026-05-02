"""Account session health-check task — runs every 6 hours.

For each AccountSession with status='active':
  1. Decrypt the stored cookies.
  2. Make a lightweight test request to the source's account page
     using curl_cffi (Kaidee / Lazada style) with the session cookies.
  3. Interpret the response:
     - 200 with expected DOM marker → session OK, update last_health_check_at
     - Redirect to /login or 401/403 → mark EXPIRED, send Discord alert
     - CAPTCHA / checkpoint page → mark BANNED, send Discord alert
     - Network error → log warning, leave status unchanged (retry next cycle)

Supported sources
-----------------
- kaidee   : GET https://www.kaidee.com/my-account  → expect <title>My Account
- lazada   : GET https://member.lazada.co.th/user/account  → expect "My Account" / "บัญชีของฉัน"
- shopee   : skip (Shopee sessions are managed externally via Scrapfly)
"""
import asyncio
from datetime import datetime, timezone
from typing import Optional

import structlog
from worker.celery_app import celery_app

log = structlog.get_logger()

# (source_id, test_url, success_marker)
_HEALTH_CONFIGS: dict[str, tuple[str, str]] = {
    "kaidee": (
        "https://www.kaidee.com/my-account",
        "my-account",
    ),
    "lazada": (
        "https://member.lazada.co.th/user/account",
        "account",
    ),
}

_LOGIN_MARKERS = [
    "/login",
    "sign-in",
    "signin",
    "/auth",
    "เข้าสู่ระบบ",
    "log in",
]
_CAPTCHA_MARKERS = [
    "captcha",
    "checkpoint",
    "verify",
    "robot",
    "blocked",
]


@celery_app.task(name="worker.tasks.session_health_task.check_all_sessions")
def check_all_sessions() -> dict:
    """Check health of all active account sessions (every 6 h)."""
    return asyncio.run(_check_all_sessions_async())


async def _check_all_sessions_async() -> dict:
    from sqlalchemy import select
    from shared.models.account_session import AccountSession, SessionStatus
    from worker.db import worker_session

    now = datetime.now(timezone.utc)
    checked = expired = banned = skipped = 0

    async with worker_session() as db:
        result = await db.execute(
            select(AccountSession).where(AccountSession.status == SessionStatus.ACTIVE)
        )
        sessions = result.scalars().all()

    for session in sessions:
        source_id = session.source_id

        if source_id not in _HEALTH_CONFIGS:
            skipped += 1
            continue

        test_url, success_marker = _HEALTH_CONFIGS[source_id]
        cookies = _decrypt_cookies(session)

        try:
            status = await _test_session(test_url, success_marker, cookies)
        except Exception as exc:
            log.warning(
                "session_health.test_error",
                session_id=session.id,
                source_id=source_id,
                error=str(exc),
            )
            continue  # leave status unchanged, retry next run

        checked += 1
        async with worker_session() as db:
            sess = await db.get(AccountSession, session.id)
            if not sess:
                continue

            sess.last_health_check_at = now

            if status == "ok":
                log.info("session_health.ok", session_id=session.id)
            elif status == "expired":
                expired += 1
                sess.status = SessionStatus.EXPIRED
                log.info("session_health.expired", session_id=session.id)
                await _notify_session_event(source_id, session.label, "expired")
            elif status == "banned":
                banned += 1
                sess.status = SessionStatus.BANNED
                log.info("session_health.banned", session_id=session.id)
                await _notify_session_event(source_id, session.label, "banned")

            await db.commit()

    result = {
        "status": "ok",
        "checked": checked,
        "expired": expired,
        "banned": banned,
        "skipped": skipped,
    }
    log.info("check_all_sessions.done", **result)
    return result


async def _test_session(
    url: str,
    success_marker: str,
    cookies: dict,
) -> str:
    """Return 'ok', 'expired', or 'banned'."""
    from curl_cffi.requests import AsyncSession as CurlSession

    async with CurlSession(impersonate="chrome124") as session:
        r = await session.get(
            url,
            cookies=cookies,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                "Accept-Language": "th-TH,th;q=0.9,en-US;q=0.8",
            },
            timeout=15,
            allow_redirects=True,
        )

    html_lower = r.text[:2000].lower()
    final_url = str(r.url).lower()

    # Check for captcha/ban first (higher priority)
    if any(m in html_lower or m in final_url for m in _CAPTCHA_MARKERS):
        return "banned"

    # Check for redirect to login
    if any(m in final_url for m in _LOGIN_MARKERS):
        return "expired"
    if r.status_code in (401, 403):
        return "expired"

    # Check success marker
    if success_marker.lower() in html_lower or success_marker.lower() in final_url:
        return "ok"

    # Ambiguous — treat as expired to be safe
    return "expired"


def _decrypt_cookies(session: "AccountSession") -> dict:
    """Decrypt cookies stored in the AccountSession row.

    Supports two storage formats:
      {"_encrypted": "<fernet-ciphertext>"}  — encrypted with Fernet
      {"_plaintext": "<json-string>"}        — plaintext fallback
    Any other dict is assumed to already be the raw cookies map.
    """
    from shared.config import get_settings
    import json

    cookies_payload = session.cookies or {}

    if "_encrypted" in cookies_payload:
        fernet_key = get_settings().fernet_key
        if not fernet_key:
            log.warning("session_health.no_fernet_key", session_id=session.id)
            return {}
        try:
            from cryptography.fernet import Fernet
            f = Fernet(fernet_key.encode())
            raw = f.decrypt(cookies_payload["_encrypted"].encode()).decode()
            return json.loads(raw)
        except Exception as exc:
            log.warning("session_health.decrypt_error", session_id=session.id, error=str(exc))
            return {}

    if "_plaintext" in cookies_payload:
        try:
            return json.loads(cookies_payload["_plaintext"])
        except Exception:
            return {}

    return cookies_payload


async def _notify_session_event(source_id: str, label: str, event: str) -> None:
    """Send Discord alert for session status change."""
    try:
        from shared.services.notifications import send_discord
        color = 0xFFA500 if event == "expired" else 0xE74C3C
        emoji = "⚠️" if event == "expired" else "🚫"
        await send_discord(
            "",
            embeds=[{
                "title": f"{emoji} Session {event}: {source_id}",
                "description": f"Session **{label}** on **{source_id}** has been marked **{event}**.",
                "color": color,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "footer": {"text": "Find-Item session monitor"},
            }],
        )
    except Exception as exc:
        log.warning("session_health.notify_error", error=str(exc))
