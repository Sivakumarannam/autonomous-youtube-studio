"""Instagram Token Watchdog.

Long-lived Instagram tokens (issued via "Business Login for Instagram")
are valid ~60 days. Rather than requiring you to manually notice and
regenerate the token every 60 days, this runs once daily and:

  1. Computes real days-remaining from when the token was last issued
     (app/integrations/instagram_token_store.py).
  2. Once within `settings.instagram_token_warn_days` of expiry, attempts
     an automatic refresh via GET https://graph.instagram.com/refresh_access_token
     (grant_type=ig_refresh_token) — the same call verified working
     manually during setup. A successful refresh resets the clock for
     another ~60 days and requires no action from you.
  3. Only sends a notification (Slack/Discord/Telegram/Email) when that
     automatic refresh actually FAILS — meaning real intervention is
     needed (e.g. the token was revoked, or permissions changed) — with
     clear regeneration steps in the message.

This means under normal operation you should see NO notifications at
all; the token silently renews itself. A notification firing is a
genuine signal something needs your attention.
"""
from __future__ import annotations

import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.core.config import settings
from app.core.logging import get_logger
from app.integrations.instagram_token_store import (
    days_remaining,
    get_current_token,
    save_refreshed_token,
)

logger = get_logger(__name__)

REFRESH_URL = "https://graph.instagram.com/refresh_access_token"


class InstagramTokenWatchdog:
    """Wraps AsyncIOScheduler with a once-daily Instagram token check."""

    def __init__(self) -> None:
        self._scheduler = AsyncIOScheduler()
        self._scheduler.add_job(
            self._run_check,
            trigger=IntervalTrigger(hours=24),
            id="instagram_token_watchdog",
            replace_existing=True,
            max_instances=1,
        )

    def start(self) -> None:
        if not self._scheduler.running:
            self._scheduler.start()
            logger.info("Instagram token watchdog started.")

    def shutdown(self) -> None:
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            logger.info("Instagram token watchdog stopped.")

    async def _notify(self, title: str, body: str, level: str) -> None:
        try:
            from app.notifications import notify
            await notify(title=title, body=body, level=level, extra={})
        except Exception as exc:
            logger.warning("Instagram token notification failed (non-fatal)", error=str(exc))

    async def _attempt_refresh(self) -> tuple[bool, str, "int | None"]:
        """Pure refresh attempt — no notification side effects. Returns
        (success, message, expires_in_seconds)."""
        token, _ = get_current_token()
        if not token:
            return False, "No Instagram access token is currently configured.", None

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                r = await client.get(
                    REFRESH_URL,
                    params={"grant_type": "ig_refresh_token", "access_token": token},
                )
                if r.is_error:
                    return False, f"{r.status_code}: {r.text[:300]}", None
                data = r.json()
                new_token = data.get("access_token")
                if not new_token:
                    return False, f"Refresh response had no access_token: {data}", None

            save_refreshed_token(new_token)
            expires_in = data.get("expires_in")
            logger.info("Instagram token refreshed successfully", expires_in_seconds=expires_in)
            return True, "Token refreshed successfully.", expires_in
        except Exception as exc:
            logger.error("Instagram token refresh failed", error=str(exc))
            return False, str(exc), None

    @staticmethod
    def manual_refresh_instructions(reason: str, remaining: "int | None" = None) -> str:
        """The human regeneration steps, shared between the failure
        notification and the dashboard button's fallback panel."""
        prefix = (
            f"Automatic refresh failed — manual action needed.\n\nReason: {reason}\n\n"
            if remaining is None
            else f"Token expires in {remaining} day(s) and automatic refresh failed "
            f"— manual action needed.\n\nReason: {reason}\n\n"
        )
        return prefix + (
            "How to fix:\n"
            "1. Go to https://developers.facebook.com/apps → your app → "
            "Use cases → Customize → Instagram API → "
            "\"API setup with Instagram login\".\n"
            "2. Under \"Generate access tokens\", click \"Generate token\" "
            "next to your Instagram account and approve on your phone.\n"
            "3. Copy the new token and set it on the server:\n"
            "   sed -i '/^INSTAGRAM_ACCESS_TOKEN=/d' .env\n"
            "   echo \"INSTAGRAM_ACCESS_TOKEN=<new token>\" >> .env\n"
            "   sed -i '/^INSTAGRAM_TOKEN_ISSUED_AT=/d' .env\n"
            "   echo \"INSTAGRAM_TOKEN_ISSUED_AT=$(date +%F)\" >> .env\n"
            "4. Restart: docker compose -f docker/docker-compose.oracle.yml up -d"
        )

    async def manual_refresh(self) -> tuple[bool, str, "int | None"]:
        """Called by the dashboard's "Refresh Now" button. Unlike the
        scheduled check, this always attempts a refresh regardless of
        days-remaining (a manual click is an explicit request to act now),
        and also fires the same notification the scheduler would, so
        Slack/Discord/etc. stay in sync with dashboard actions too."""
        success, message, expires_in = await self._attempt_refresh()
        if success:
            await self._notify(
                title="Instagram token refreshed ✅",
                body=(
                    "Manually triggered from the dashboard — token refreshed "
                    "and valid for another ~60 days."
                ),
                level="success",
            )
        else:
            await self._notify(
                title="Instagram token refresh failed ❌",
                body=self.manual_refresh_instructions(message),
                level="error",
            )
        return success, message, expires_in

    async def _run_check(self) -> None:
        if not settings.instagram_enabled:
            return

        remaining = days_remaining()
        if remaining is None:
            # No issued_at date on record at all — can't compute a real
            # countdown. This happens once, on first boot after this
            # feature was added, before any token has been through the
            # store. Treat it the same as "close to expiry" so it gets
            # refreshed (and its issued_at recorded) on the next check
            # rather than silently never warning.
            logger.warning(
                "Instagram token has no known issue date — attempting refresh "
                "now to establish one."
            )
            remaining = 0

        logger.info("Instagram token check", days_remaining=remaining)

        if remaining > settings.instagram_token_warn_days:
            return  # still comfortably valid, nothing to do

        success, message, expires_in = await self._attempt_refresh()
        if success:
            await self._notify(
                title="Instagram token refreshed ✅",
                body=(
                    "Your Instagram access token was automatically refreshed "
                    "and is now valid for another ~60 days. No action needed."
                ),
                level="success",
            )
        else:
            await self._notify(
                title=f"Instagram access token expires in {remaining} day(s) ❌",
                body=self.manual_refresh_instructions(message, remaining=remaining),
                level="error",
            )


_watchdog: InstagramTokenWatchdog | None = None


def get_instagram_token_watchdog() -> InstagramTokenWatchdog:
    global _watchdog
    if _watchdog is None:
        _watchdog = InstagramTokenWatchdog()
    return _watchdog
