"""Chat API routes — Studio Assistant chatbot.

WebSocket:
  /ws/chat         — bidirectional chat (auth via yt_studio_session cookie)

REST (all require dashboard auth):
  GET  /api/v1/chat/kb/docs           — list knowledge base documents
  POST /api/v1/chat/kb/docs           — ingest a new document
  DELETE /api/v1/chat/kb/docs/{doc_id} — delete a document

Dashboard partials (auth guarded):
  GET /dashboard/partials/knowledge-base — render _knowledge_base.html
"""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.database.connection import get_db
from app.database.models.chat import ChatSession, ChatMessage, ChatUnresolved, KnowledgeDoc
from app.chatbot.engine import answer_question
from app.chatbot.escalation import escalate
from app.chatbot.knowledge_base import (
    ingest_document,
    delete_document,
    list_documents,
    has_any_knowledge_docs,
    TOPIC_KNOWLEDGE,
)
from app.chatbot.context_builder import get_suggested_questions
from app.web.auth import require_dashboard_auth
from app.web.templates import templates

logger = get_logger(__name__)

ws_router = APIRouter()   # mounted at /ws
api_router = APIRouter()  # mounted at /api/v1/chat
dash_router = APIRouter() # mounted at /dashboard/partials

_COOKIE_NAME = "yt_studio_session"

# ---------------------------------------------------------------------------
# Cookie validation (same logic as websocket.py)
# ---------------------------------------------------------------------------

def _cookie_valid(cookie_value: str) -> bool:
    token = settings.dashboard_auth_token
    if not token:
        return True  # dev mode
    sig = hmac.new(token.encode(), token.encode(), hashlib.sha256).hexdigest()
    try:
        return secrets.compare_digest(cookie_value, sig)
    except Exception:
        return False


# ---------------------------------------------------------------------------
# 24-hour history cleanup (called on WS connect + startup)
# ---------------------------------------------------------------------------

async def cleanup_old_messages(session: AsyncSession) -> int:
    """Delete chat messages older than 24 hours. Returns row count."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    result = await session.execute(
        delete(ChatMessage).where(ChatMessage.created_at < cutoff)
    )
    # Also delete empty sessions
    await session.execute(
        delete(ChatSession).where(ChatSession.last_active_at < cutoff)
    )
    await session.commit()
    deleted = result.rowcount or 0
    if deleted:
        logger.info("Pruned old chat messages", count=deleted)
    return deleted


# ---------------------------------------------------------------------------
# WebSocket — /ws/chat
# ---------------------------------------------------------------------------

@ws_router.websocket("/chat")
async def chat_websocket(websocket: WebSocket) -> None:
    """Bidirectional chat WebSocket.

    Inbound messages (JSON):
      {"type": "question", "text": "..."}   — ask a question
      {"type": "flag"}                       — escalate last answer
      {"type": "ping"}                       — keepalive

    Outbound messages (JSON):
      {"type": "token", "text": "..."}       — streamed response chunk
      {"type": "done", "sources": [...], "low_confidence": bool}
      {"type": "escalated", "id": "..."}     — escalation confirmed
      {"type": "suggested", "questions": [...]}
      {"type": "history", "messages": [...]} — last 24h history on connect
      {"type": "error", "text": "..."}
    """
    cookie_value = websocket.cookies.get(_COOKIE_NAME, "")
    if not _cookie_valid(cookie_value):
        await websocket.close(code=1008)
        logger.warning("Chat WebSocket rejected — invalid session cookie")
        return

    await websocket.accept()

    # Each WS connection gets its own session (in the DB sense)
    chat_session_id = uuid.uuid4()
    last_question: str = ""
    last_context: str = ""

    # Use a fresh DB session for the lifetime of this connection
    from app.database.connection import get_session_factory
    factory = get_session_factory()

    async with factory() as db:
        # Cleanup old messages on connect
        await cleanup_old_messages(db)

        # Create a chat session row
        chat_session = ChatSession(
            id=chat_session_id,
            created_at=datetime.now(timezone.utc),
            last_active_at=datetime.now(timezone.utc),
        )
        db.add(chat_session)
        await db.commit()

        # Send recent history (last 20 messages from the last 24h)
        history_result = await db.execute(
            select(ChatMessage)
            .where(ChatMessage.created_at >= datetime.now(timezone.utc) - timedelta(hours=24))
            .order_by(ChatMessage.created_at.asc())
            .limit(20)
        )
        history_rows = history_result.scalars().all()
        if history_rows:
            await websocket.send_json({
                "type": "history",
                "messages": [
                    {
                        "role": m.role,
                        "content": m.content,
                        "sources": json.loads(m.sources_json) if m.sources_json else [],
                    }
                    for m in history_rows
                ],
            })

        # Send suggested questions
        suggestions = await get_suggested_questions(db)
        await websocket.send_json({"type": "suggested", "questions": suggestions})

        # Keep conversation memory for context (last 6 messages)
        conv_history: list[dict] = [
            {"role": m.role, "content": m.content} for m in history_rows[-6:]
        ]

        try:
            while True:
                raw = await websocket.receive_text()
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    await websocket.send_json({"type": "error", "text": "Invalid JSON"})
                    continue

                msg_type = msg.get("type", "")

                if msg_type == "ping":
                    await websocket.send_json({"type": "pong"})
                    continue

                if msg_type == "flag":
                    # User manually escalates the last answer
                    if last_question:
                        record = await escalate(
                            db,
                            question=last_question,
                            context_snapshot=last_context,
                            chat_session_id=chat_session_id,
                        )
                        await websocket.send_json({
                            "type": "escalated",
                            "id": str(record.id),
                            "text": "I've flagged this for investigation. You'll receive a notification when it's resolved.",
                        })
                    continue

                if msg_type != "question":
                    continue

                question = (msg.get("text") or "").strip()
                if not question:
                    continue

                last_question = question

                # Save user message
                user_msg = ChatMessage(
                    id=uuid.uuid4(),
                    session_id=chat_session_id,
                    role="user",
                    content=question,
                    created_at=datetime.now(timezone.utc),
                )
                db.add(user_msg)
                await db.commit()
                conv_history.append({"role": "user", "content": question})

                # Collect streamed tokens
                streamed_tokens: list[str] = []

                async def on_token(token: str) -> None:
                    streamed_tokens.append(token)
                    await websocket.send_json({"type": "token", "text": token})

                # Run the answer engine
                try:
                    sources, low_confidence = await answer_question(
                        question=question,
                        session=db,
                        on_token=on_token,
                        history=conv_history[:-1],  # exclude the just-added user msg
                    )
                except Exception as exc:
                    logger.exception("Chat engine error", error=str(exc))
                    await websocket.send_json({"type": "error", "text": "An error occurred generating the answer."})
                    continue

                full_answer = "".join(streamed_tokens)
                last_context = full_answer[:500]

                # Save assistant message
                asst_msg = ChatMessage(
                    id=uuid.uuid4(),
                    session_id=chat_session_id,
                    role="assistant",
                    content=full_answer,
                    sources_json=json.dumps(sources) if sources else None,
                    created_at=datetime.now(timezone.utc),
                )
                db.add(asst_msg)

                # Update session activity
                chat_session.last_active_at = datetime.now(timezone.utc)
                await db.commit()

                conv_history.append({"role": "assistant", "content": full_answer})
                # Keep history bounded
                if len(conv_history) > 12:
                    conv_history = conv_history[-12:]

                # Send done signal
                await websocket.send_json({
                    "type": "done",
                    "sources": sources,
                    "low_confidence": low_confidence,
                })

                # Auto-escalate if low confidence
                if low_confidence:
                    record = await escalate(
                        db,
                        question=question,
                        context_snapshot=last_context,
                        chat_session_id=chat_session_id,
                    )
                    await websocket.send_json({
                        "type": "escalated",
                        "id": str(record.id),
                        "text": "I'm not fully certain about this answer — I've flagged it for investigation.",
                    })

        except WebSocketDisconnect:
            logger.info("Chat WebSocket disconnected", session=str(chat_session_id))
        except Exception:
            logger.exception("Chat WebSocket error")


# ---------------------------------------------------------------------------
# REST — Knowledge Base management
# ---------------------------------------------------------------------------

class IngestDocRequest(BaseModel):
    title: str
    text: str
    topic_id: str = TOPIC_KNOWLEDGE


@api_router.get("/kb/docs", dependencies=[Depends(require_dashboard_auth)])
async def list_kb_docs(db: AsyncSession = Depends(get_db)):
    docs = await list_documents(db)
    return [
        {
            "id": str(d.id),
            "title": d.title,
            "source_type": d.source_type,
            "topic_id": d.topic_id,
            "chunk_count": d.chunk_count,
            "active": d.active,
            "ingested_at": d.ingested_at.isoformat(),
        }
        for d in docs
    ]


@api_router.post("/kb/docs", dependencies=[Depends(require_dashboard_auth)], status_code=201)
async def ingest_kb_doc(body: IngestDocRequest, db: AsyncSession = Depends(get_db)):
    try:
        doc = await ingest_document(
            session=db,
            title=body.title,
            text=body.text,
            topic_id=body.topic_id,
        )
        return {"id": str(doc.id), "chunk_count": doc.chunk_count}
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@api_router.delete("/kb/docs/{doc_id}", dependencies=[Depends(require_dashboard_auth)])
async def delete_kb_doc(doc_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    deleted = await delete_document(db, doc_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Document not found")
    return {"deleted": True}


# ---------------------------------------------------------------------------
# Dashboard partial — Knowledge Base panel
# ---------------------------------------------------------------------------

@dash_router.get(
    "/knowledge-base",
    response_class=HTMLResponse,
    dependencies=[Depends(require_dashboard_auth)],
    include_in_schema=False,
)
async def kb_partial(request: Request, db: AsyncSession = Depends(get_db)):
    docs = await list_documents(db)
    return templates.TemplateResponse(
        request,
        "dashboard/_knowledge_base.html",
        {"docs": docs},
    )
