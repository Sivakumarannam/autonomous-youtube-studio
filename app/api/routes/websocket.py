"""WebSocket endpoint for real-time dashboard updates (Phase 5, item 1).

Clients connect once and receive JSON events for:
  - pipeline_run.created / pipeline_run.updated  (status, current_stage changes)
  - upload.updated                               (publish_status/status changes)
  - scheduler.tick                               (due_count, succeeded, failed)

The dashboard's JS (see app/templates/base.html) listens on this socket and
triggers HTMX partial refreshes — it does not render HTML itself.

Auth: the browser must hold a valid `yt_studio_session` cookie (set at login).
      Unauthenticated connections are closed with code 1008 (Policy Violation).
      Development without DASHBOARD_AUTH_TOKEN allows open access; production rejects.
"""
from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.logging import get_logger
from app.web.auth import COOKIE_NAME, is_ws_session_valid
from app.websocket.manager import get_connection_manager

logger = get_logger(__name__)

router = APIRouter()


@router.websocket("/pipeline")
async def pipeline_updates(websocket: WebSocket) -> None:
    # Validate session cookie before accepting the connection.
    cookie_value = websocket.cookies.get(COOKIE_NAME)
    if not is_ws_session_valid(cookie_value):
        await websocket.close(code=1008)  # 1008 = Policy Violation
        logger.warning("WebSocket connection rejected — invalid or missing session cookie.")
        return

    manager = get_connection_manager()
    await manager.connect(websocket)
    try:
        while True:
            # Clients don't need to send anything; we just need to detect
            # disconnects. Any inbound message is ignored.
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        logger.exception("WebSocket connection error.")
        manager.disconnect(websocket)
