"""In-process WebSocket connection manager.

Design rationale (Phase 5, item 1):
  At this project's scale (single FastAPI process, one Uvicorn worker, no
  horizontal scaling), an in-process broadcast list is sufficient to fan
  live updates out to connected dashboard clients. A pub/sub broker such as
  Redis would only be needed once the app runs across multiple processes or
  machines that need to share connection state — that is not the case here.
  If the app ever moves to multi-worker/multi-instance deployment, this
  manager would need to be replaced by a shared broker (Redis pub/sub,
  etc.) so that a broadcast triggered on worker A reaches clients connected
  to worker B.

Failure isolation: a broadcast must never raise into the caller (repository/
service code paths that are not primarily about WebSockets). Dead or slow
sockets are dropped silently.
"""
from __future__ import annotations

import json
from typing import Any

from fastapi import WebSocket

from app.core.logging import get_logger

logger = get_logger(__name__)


class ConnectionManager:
    """Tracks connected WebSocket clients and broadcasts JSON messages."""

    def __init__(self) -> None:
        self._connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections.append(websocket)
        logger.info(
            "WebSocket client connected.", total_connections=len(self._connections)
        )

    def disconnect(self, websocket: WebSocket) -> None:
        if websocket in self._connections:
            self._connections.remove(websocket)
        logger.info(
            "WebSocket client disconnected.", total_connections=len(self._connections)
        )

    async def broadcast(self, message: dict[str, Any]) -> None:
        """Send a JSON message to every connected client.

        Safe to call from anywhere (repositories, services, the scheduler)
        even when zero clients are connected. Never raises.
        """
        if not self._connections:
            return

        payload = json.dumps(message, default=str)
        dead: list[WebSocket] = []

        for connection in self._connections:
            try:
                await connection.send_text(payload)
            except Exception:
                dead.append(connection)

        for connection in dead:
            self.disconnect(connection)


# Module-level singleton — mirrors the pattern used by
# app.scheduler.scheduler.get_scheduler().
_manager: ConnectionManager | None = None


def get_connection_manager() -> ConnectionManager:
    global _manager
    if _manager is None:
        _manager = ConnectionManager()
    return _manager


async def broadcast_safe(message: dict[str, Any]) -> None:
    """Broadcast helper that swallows all errors.

    Used from non-WebSocket code (repositories, scheduler) so that a
    WebSocket failure can never break a DB write or pipeline stage.
    """
    try:
        await get_connection_manager().broadcast(message)
    except Exception:
        logger.exception("WebSocket broadcast failed; continuing without it.")