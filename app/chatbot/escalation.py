"""Escalation handler — saves unresolved questions and fires notifications."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.database.models.chat import ChatUnresolved

logger = get_logger(__name__)


async def escalate(
    session: AsyncSession,
    question: str,
    context_snapshot: Optional[str] = None,
    chat_session_id: Optional[uuid.UUID] = None,
) -> ChatUnresolved:
    """Persist an unresolved question and fire a notification.

    This is called when:
    - The LLM returned __LOW_CONFIDENCE__ in its response, OR
    - The user manually clicks the Flag button
    """
    record = ChatUnresolved(
        id=uuid.uuid4(),
        session_id=chat_session_id,
        question=question,
        context_snapshot=context_snapshot,
        created_at=datetime.now(timezone.utc),
    )
    session.add(record)
    await session.commit()
    await session.refresh(record)

    logger.info(
        "Chatbot question escalated",
        escalation_id=str(record.id),
        question=question[:100],
    )

    # Fire async notification (non-blocking — failure never crashes the chat)
    try:
        from app.notifications.service import NotificationService
        notifier = NotificationService()
        await notifier.send(
            title="Studio Assistant — Unanswered Question",
            body=(
                f"A question was flagged for investigation:\n\n"
                f"**{question}**\n\n"
                f"Escalation ID: {record.id}\n"
                f"Time: {record.created_at.strftime('%Y-%m-%d %H:%M UTC')}"
            ),
            level="warning",
        )
    except Exception as exc:
        logger.warning("Escalation notification failed", error=str(exc))

    return record
