"""YouTube Token Watchdog.

Access tokens (~1 hour) are refreshed on demand by YouTubeAuthManager using
YOUTUBE_CLIENT_ID / YOUTUBE_CLIENT_SECRET / YOUTUBE_REFRESH_TOKEN from .env.

This watchdog:
  1. Periodically POSTs to Google's token endpoint to verify the refresh token.
  2. On success: updates last-ok state (silent under normal operation).
  3. On failure: high-priority Slack/Discord/Telegram/Email alert with re-auth steps.
  4. Supports a dashboard "Refresh Token Now" button (same check, always notifies).

Unlike Instagram, Google does not let us mint a *new* refresh token without
browser consent once the current one is revoked/expired.
"""
from __future__ import annotations

from datetime import datetime, timezone

import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.core.config import settings
from app.core.logging import get_logger
from app.integrations.youtube_token_store import days_remaining, mark_token_ok

logger = get_logger(__name__)

TOKEN_URL = "https://oauth2.googleapis.com/token"


class YouTubeTokenWatchdog:
    def __init__(self) -> None:
        hours = max(1, int(getattr(settings, "youtube_token_check_hours", 12)))
        self._scheduler = AsyncIOScheduler()
        self._scheduler.add_job(
            self._run_check,
            trigger=IntervalTrigger(hours=hours),
            id="youtube_token_watchdog",
            replace_existing=True,
            max_instances=1,
        )
        self._last_alert_at: datetime | None = None

    def start(self) -> None:
        if not self._scheduler.running:
            self._scheduler.start()
            logger.info("YouTube token watchdog started.")

    def shutdown(self) -> None:
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            logger.info("YouTube token watchdog stopped.")

    async def _notify(self, title: str, body: str, level: str) -> None:
        try:
            from app.notifications import notify

            await notify(title=title, body=body, level=level, extra={})
        except Exception as exc:
            logger.warning("YouTube token notification failed", error=str(exc))

    def _configured(self) -> bool:
        return bool(
            settings.youtube_client_id
            and settings.youtube_client_secret
            and settings.youtube_refresh_token
        )

    async def _attempt_refresh(self) -> tuple[bool, str]:
        if not self._configured():
            return False, (
                "YouTube OAuth not fully configured. "
                "Set YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET, and "
                "YOUTUBE_REFRESH_TOKEN in .env"
            )

        payload = {
            "client_id": settings.youtube_client_id,
            "client_secret": settings.youtube_client_secret,
            "refresh_token": settings.youtube_refresh_token,
            "grant_type": "refresh_token",
        }
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                r = await client.post(TOKEN_URL, data=payload)
            if r.status_code != 200:
                return False, f"{r.status_code}: {r.text[:400]}"
            data = r.json()
            if not data.get("access_token"):
                return False, f"No access_token in response: {data}"
            return True, f"Access token OK (expires_in={data.get('expires_in', '?')}s)"
        except Exception as exc:
            return False, str(exc)

    @staticmethod
    def reauth_instructions(reason: str, remaining: int | None = None) -> str:
        prefix = (
            f"YouTube OAuth refresh FAILED — uploads will stop until fixed.\n\n"
            f"Reason: {reason}\n\n"
        )
        if remaining is not None:
            prefix = (
                f"Token window: ~{remaining} day(s) left and refresh check failed.\n\n"
                f"Reason: {reason}\n\n"
            )
        return prefix + (
            "How to fix:\n"
            "1. Google Cloud Console → enable YouTube Data API v3.\n"
            "2. Use a Desktop OAuth client; run offline consent "
            "(access_type=offline, prompt=consent).\n"
            "3. Put the new values in .env:\n"
            "     YOUTUBE_CLIENT_ID=...\n"
            "     YOUTUBE_CLIENT_SECRET=...\n"
            "     YOUTUBE_REFRESH_TOKEN=1//...\n"
            "     YOUTUBE_TOKEN_ISSUED_AT=$(date +%F)\n"
            "4. Restart: docker compose -f docker/docker-compose.oracle.yml up -d\n"
        )

    async def manual_refresh(self) -> tuple[bool, str]:
        """Dashboard button — always attempt + notify."""
        success, message = await self._attempt_refresh()
        if success:
            mark_token_ok()
            await self._notify(
                title="YouTube token check OK ✅",
                body=(
                    "Manually triggered from the dashboard — refresh token is valid. "
                    "Access tokens will continue to auto-refresh on upload."
                ),
                level="success",
            )
        else:
            await self._notify(
                title="YouTube token refresh failed ❌",
                body=self.reauth_instructions(message),
                level="error",
            )
        return success, message

    async def _run_check(self) -> None:
        if not (
            settings.youtube_client_id
            or settings.youtube_client_secret
            or settings.youtube_refresh_token
        ):
            return

        remaining = days_remaining()
        warn_days = int(getattr(settings, "youtube_token_warn_days", 2))

        logger.info("YouTube token check starting", days_remaining=remaining)

        # Always verify the token still works (not only near expiry)
        ok, message = await self._attempt_refresh()
        if ok:
            mark_token_ok()
            logger.info("YouTube token check OK", detail=message)
            # Soft warning when close to configured lifetime
            if remaining is not None and remaining <= warn_days:
                await self._notify(
                    title=f"YouTube refresh token window: {remaining} day(s) left",
                    body=(
                        "Access token refresh still works today. "
                        "If your Google app is in Testing mode, refresh tokens may "
                        "expire in ~7 days — plan a re-auth before uploads fail.\n\n"
                        + self.reauth_instructions(
                            "Proactive warning (token still working)", remaining
                        )
                    ),
                    level="warning",
                )
            return

        now = datetime.now(timezone.utc)
        if self._last_alert_at and (now - self._last_alert_at).total_seconds() < 6 * 3600:
            logger.warning("YouTube token still failing (alert suppressed)", detail=message)
            return

        self._last_alert_at = now
        logger.error("YouTube token check FAILED", detail=message)
        await self._notify(
            title="🚨 YouTube OAuth token FAILED",
            body=self.reauth_instructions(message, remaining),
            level="error",
        )


_watchdog: YouTubeTokenWatchdog | None = None


def get_youtube_token_watchdog() -> YouTubeTokenWatchdog:
    global _watchdog
    if _watchdog is None:
        _watchdog = YouTubeTokenWatchdog()
    return _watchdog
