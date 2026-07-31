"""Notification system for Autonomous YouTube Studio.

Supports: Email (Gmail SMTP), Slack, Discord, Telegram.
Each provider is enabled independently via environment variables.
"""
from app.notifications.service import NotificationService, notify

__all__ = ["NotificationService", "notify"]
