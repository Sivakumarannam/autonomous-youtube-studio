import time
from typing import Optional

import httpx

from app.core.logging import get_logger

logger = get_logger(__name__)


class YouTubeAuthManager:
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        refresh_token: str,
        token_url: str = "https://oauth2.googleapis.com/token",
        http_client: Optional[httpx.AsyncClient] = None,
    ):
        self.client_id = client_id
        self.client_secret = client_secret
        self.refresh_token = refresh_token
        self.token_url = token_url
        self.http_client = http_client or httpx.AsyncClient(timeout=30)

        self._access_token: Optional[str] = None
        self._expires_at: float = 0.0

    async def get_access_token(self) -> str:
        if self._access_token and time.time() < self._expires_at - 30:
            return self._access_token

        return await self.refresh_access_token()

    async def refresh_access_token(self) -> str:
        payload = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "refresh_token": self.refresh_token,
            "grant_type": "refresh_token",
        }

        try:
            response = await self.http_client.post(self.token_url, data=payload)

            if response.status_code != 200:
                logger.error(
                    "YouTube token refresh failed.",
                    status_code=response.status_code,
                    response_text=response.text,
                )

            response.raise_for_status()

            data = response.json()

            access_token = data.get("access_token")
            expires_in = int(data.get("expires_in", 3600))

            if not access_token:
                raise RuntimeError("No access_token returned in token refresh response.")

            self._access_token = access_token
            self._expires_at = time.time() + expires_in

            return access_token

        except httpx.HTTPStatusError as e:
            logger.error(
                "YouTube token refresh HTTP error.",
                status_code=e.response.status_code,
                response_text=e.response.text,
            )
            raise

        except Exception as e:
            logger.error("YouTube token refresh failed with unexpected error.", error=str(e))
            raise

    async def close(self) -> None:
        await self.http_client.aclose()