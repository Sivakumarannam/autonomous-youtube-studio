"""Minimal shared-secret auth guard for the dashboard and metrics endpoints.

Accepts (in order of precedence):
  1. Session cookie `yt_studio_session` set by the /login form
  2. `Authorization: Bearer <token>` header
  3. HTTP Basic auth with the token as the password (username is ignored)
"""
from __future__ import annotations

import hashlib
import hmac
import secrets

from fastapi import Cookie, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from fastapi.security import (
    HTTPAuthorizationCredentials,
    HTTPBasic,
    HTTPBasicCredentials,
    HTTPBearer,
)

from app.core.config import settings

_bearer_scheme = HTTPBearer(auto_error=False)
_basic_scheme = HTTPBasic(auto_error=False)

COOKIE_NAME = "yt_studio_session"


def _token_matches(candidate: str) -> bool:
    if not settings.dashboard_auth_token:
        return False
    return secrets.compare_digest(candidate, settings.dashboard_auth_token)


def _make_cookie_value(token: str) -> str:
    """HMAC-sign the token so a cookie can't be forged without knowing the token."""
    sig = hmac.new(token.encode(), token.encode(), hashlib.sha256).hexdigest()
    return f"{sig}"


def _cookie_valid(cookie_value: str) -> bool:
    if not settings.dashboard_auth_token:
        return False
    expected = _make_cookie_value(settings.dashboard_auth_token)
    return secrets.compare_digest(cookie_value, expected)


def make_session_cookie(token: str) -> str:
    """Return the cookie value to set after successful login."""
    return _make_cookie_value(token)


def is_ws_session_valid(cookie_value: str | None) -> bool:
    """Validate dashboard session cookie for WebSocket upgrades.

    - Production with no DASHBOARD_AUTH_TOKEN → reject (fail closed)
    - Development with no token → allow (open local dev)
    - Otherwise require a valid HMAC session cookie
    """
    if not settings.dashboard_auth_token:
        if settings.app_env == "development":
            return True
        return False
    if not cookie_value:
        return False
    return _cookie_valid(cookie_value)


async def require_dashboard_auth(
    request: Request,
    bearer: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    basic: HTTPBasicCredentials | None = Depends(_basic_scheme),
    yt_studio_session: str | None = Cookie(default=None),
) -> None:
    # Dev convenience: no token configured → open access
    if not settings.dashboard_auth_token:
        if settings.app_env == "development":
            import structlog as _sl
            _sl.get_logger(__name__).warning(
                "DASHBOARD_AUTH_TOKEN not set — dashboard is open to everyone. "
                "Add it in Replit Secrets before deploying to production."
            )
            return
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Dashboard auth is not configured: set DASHBOARD_AUTH_TOKEN.",
        )

    # 1. Session cookie (browser login)
    if yt_studio_session and _cookie_valid(yt_studio_session):
        return

    # 2. Bearer token
    if bearer is not None and _token_matches(bearer.credentials):
        return

    # 3. HTTP Basic
    if basic is not None and _token_matches(basic.password):
        return

    # For browser requests (Accept: text/html) redirect to login page
    accept = request.headers.get("accept", "")
    if "text/html" in accept:
        raise HTTPException(
            status_code=status.HTTP_307_TEMPORARY_REDIRECT,
            headers={"Location": f"/login?next={request.url.path}"},
        )

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated.",
        headers={"WWW-Authenticate": "Bearer"},
    )
