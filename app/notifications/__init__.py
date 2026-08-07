"""Notification system for Autonomous YouTube Studio.

Supports: Email (Gmail SMTP), Slack, Discord, Telegram.
Each provider is enabled independently via environment variables.
"""
from app.notifications.service import NotificationService, notify
from app.notifications.high_alert import high_alert

__all__ = ["NotificationService", "notify", "high_alert"]
