"""Central notification dispatcher — calls all enabled providers."""
from __future__ import annotations

import asyncio
from typing import Optional

import structlog

from app.core.config import settings

logger = structlog.get_logger(__name__)


class NotificationService:
    """Send event notifications to all configured channels."""

    async def send(
        self,
        title: str,
        body: str,
        level: str = "info",  # "info" | "success" | "warning" | "error"
        extra: Optional[dict] = None,
    ) -> None:
        """Fire and forget to all enabled providers."""
        tasks = []

        if settings.notification_email_enabled:
            tasks.append(self._send_email(title, body, level, extra))

        if settings.notification_slack_enabled:
            tasks.append(self._send_slack(title, body, level, extra))

        if settings.notification_discord_enabled:
            tasks.append(self._send_discord(title, body, level, extra))

        if settings.notification_telegram_enabled:
            tasks.append(self._send_telegram(title, body, level, extra))

        if getattr(settings, "notification_whatsapp_enabled", False):
            tasks.append(self._send_whatsapp(title, body, level, extra))

        if not tasks:
            return

        results = await asyncio.gather(*tasks, return_exceptions=True)
        for r in results:
            if isinstance(r, Exception):
                logger.warning("Notification provider failed", error=str(r))

    # ------------------------------------------------------------------ email
    async def _send_email(self, title, body, level, extra):
        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart

        msg = MIMEMultipart("alternative")
        sender = settings.notification_email_from or getattr(settings, "smtp_user", "")
        msg["Subject"] = f"[YouTube Studio] {title}"
        msg["From"] = sender
        msg["To"] = settings.notification_email_to

        icon = {"info": "ℹ️", "success": "✅", "warning": "⚠️", "error": "❌"}.get(level, "ℹ️")
        html = f"""
        <html><body style="font-family:sans-serif;background:#0f1117;color:#e6e8ef;padding:20px">
          <div style="max-width:520px;margin:auto;background:#161925;border-radius:10px;padding:24px;border:1px solid #262b3a">
            <h2 style="margin:0 0 12px;font-size:1.1rem">{icon} {title}</h2>
            <p style="margin:0 0 16px;color:#8b90a3;line-height:1.6">{body}</p>
            {"".join(f'<p style="margin:4px 0;font-size:0.85rem;color:#8b90a3"><b>{k}:</b> {v}</p>' for k,v in (extra or {}).items())}
            <p style="margin:16px 0 0;font-size:0.75rem;color:#555">Autonomous YouTube Studio</p>
          </div>
        </body></html>"""

        msg.attach(MIMEText(body, "plain"))
        msg.attach(MIMEText(html, "html"))

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._smtp_send, msg)
        logger.info("Email notification sent", title=title)

    def _smtp_send(self, msg):
        import smtplib
        # Support both notification_email_from and smtp_user as the sender
        sender = settings.notification_email_from or getattr(settings, "smtp_user", "")
        password = settings.notification_email_password or getattr(settings, "smtp_password", "")
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
            server.ehlo()
            server.starttls()
            server.login(sender, password)
            server.sendmail(
                sender,
                settings.notification_email_to,
                msg.as_string(),
            )

    # ------------------------------------------------------------------ slack
    async def _send_slack(self, title, body, level, extra):
        import httpx
        color = {"info": "#5b8cff", "success": "#3ecf8e", "warning": "#f5c04c", "error": "#ff6b6b"}.get(level, "#5b8cff")
        payload = {
            "attachments": [{
                "color": color,
                "title": title,
                "text": body,
                "fields": [{"title": k, "value": str(v), "short": True} for k, v in (extra or {}).items()],
                "footer": "Autonomous YouTube Studio",
            }]
        }
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(settings.slack_webhook_url, json=payload)
            r.raise_for_status()
        logger.info("Slack notification sent", title=title)

    # ---------------------------------------------------------------- discord
    async def _send_discord(self, title, body, level, extra):
        import httpx
        color = {"info": 0x5b8cff, "success": 0x3ecf8e, "warning": 0xf5c04c, "error": 0xff6b6b}.get(level, 0x5b8cff)
        embed = {
            "title": title,
            "description": body,
            "color": color,
            "fields": [{"name": k, "value": str(v), "inline": True} for k, v in (extra or {}).items()],
            "footer": {"text": "Autonomous YouTube Studio"},
        }
        payload = {"embeds": [embed]}
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(settings.discord_webhook_url, json=payload)
            r.raise_for_status()
        logger.info("Discord notification sent", title=title)

    # --------------------------------------------------------------- telegram
    async def _send_telegram(self, title, body, level, extra):
        import httpx
        icon = {"info": "ℹ️", "success": "✅", "warning": "⚠️", "error": "❌"}.get(level, "ℹ️")
        lines = [f"{icon} *{title}*", "", body]
        if extra:
            lines.append("")
            for k, v in extra.items():
                lines.append(f"• *{k}:* {v}")
        text = "\n".join(lines)
        url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(url, json={
                "chat_id": settings.telegram_chat_id,
                "text": text,
                "parse_mode": "Markdown",
            })
            r.raise_for_status()
        logger.info("Telegram notification sent", title=title)


    # --------------------------------------------------------------- whatsapp
    async def _send_whatsapp(self, title, body, level, extra):
        """Send via CallMeBot free WhatsApp API (https://www.callmebot.com)."""
        import urllib.parse
        import httpx
        phone = getattr(settings, "whatsapp_phone", "")
        apikey = getattr(settings, "whatsapp_apikey", "")
        if not phone or not apikey:
            logger.warning("WhatsApp not configured — skipping")
            return
        icon = {"info": "ℹ️", "success": "✅", "warning": "⚠️", "error": "❌"}.get(level, "ℹ️")
        lines = [f"{icon} *{title}*", body]
        if extra:
            for k, v in extra.items():
                lines.append(f"• {k}: {v}")
        lines.append("— Autonomous YouTube Studio")
        text = urllib.parse.quote("\n".join(lines))
        url = f"https://api.callmebot.com/whatsapp.php?phone={phone}&text={text}&apikey={apikey}"
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(url)
            r.raise_for_status()
        logger.info("WhatsApp notification sent", title=title)


# Module-level singleton
_svc = NotificationService()


async def notify(
    title: str,
    body: str,
    level: str = "info",
    extra: Optional[dict] = None,
) -> None:
    """Convenience wrapper — call from anywhere without instantiating the service."""
    await _svc.send(title, body, level, extra)
