import asyncio
import inspect
from pathlib import Path
from typing import Any, Dict, Optional

import httpx

from .client import YouTubeApiClient


class YouTubeUploader:
    def __init__(self, api_client: YouTubeApiClient):
        self.api_client = api_client
        self.upload_url = "https://www.googleapis.com/upload/youtube/v3/videos"

    async def upload_video(
        self,
        file_path: str,
        metadata: Dict[str, Any],
        chunk_size: int = 256 * 1024,
    ) -> Dict[str, Any]:
        total_size = Path(file_path).stat().st_size
        if total_size == 0:
            raise RuntimeError(f"Cannot upload empty file: {file_path}")

        upload_session = await self._init_resumable_upload(metadata, total_size)

        result: Optional[Dict[str, Any]] = None
        offset = 0

        with open(file_path, "rb") as file_handle:
            while True:
                chunk = file_handle.read(chunk_size)
                if not chunk:
                    break

                start = offset
                end = offset + len(chunk) - 1
                is_last_chunk = (offset + len(chunk)) >= total_size

                result = await self._upload_chunk(
                    upload_session,
                    chunk,
                    start=start,
                    end=end,
                    total_size=total_size,
                )
                offset += len(chunk)

                if is_last_chunk and result is not None:
                    break

        if result is None:
            raise RuntimeError(
                "Upload completed without a final response from YouTube — "
                "the video resource was never returned."
            )

        return result

    async def _init_resumable_upload(
        self, metadata: Dict[str, Any], total_size: int
    ) -> str:
        headers = await self.api_client._headers()
        headers.update(
            {
                "X-Upload-Content-Type": "video/mp4",
                "X-Upload-Content-Length": str(total_size),
            }
        )
        response = await self.api_client.session.post(
            self.upload_url,
            headers=headers,
            params={"uploadType": "resumable", "part": "snippet,status"},
            json=metadata,
        )
        await self._maybe_await(response.raise_for_status())
        location = response.headers.get("Location")
        if not location:
            raise RuntimeError("Resumable upload session did not return Location header")
        return location

    async def _upload_chunk(
        self,
        upload_url: str,
        chunk: bytes,
        start: int,
        end: int,
        total_size: int,
    ) -> Optional[Dict[str, Any]]:
        headers = {
            "Content-Type": "video/mp4",
            "Content-Length": str(len(chunk)),
            "Content-Range": f"bytes {start}-{end}/{total_size}",
        }
        response = await self.api_client.session.put(
            upload_url,
            content=chunk,
            headers=headers,
        )

        if response.status_code == 308:
            # Resume Incomplete — expected for every chunk except the last.
            return None

        if response.status_code in (200, 201):
            # Final chunk accepted; YouTube returns the created video resource.
            return await self._maybe_await(response.json())

        await self._maybe_await(response.raise_for_status())
        return None

    async def upload_thumbnail(self, video_id: str, thumbnail_path: str) -> None:
        url = f"https://www.googleapis.com/upload/youtube/v3/thumbnails/set"
        headers = await self.api_client._headers()
        headers.update({"Content-Type": "application/octet-stream"})
        data = await asyncio.to_thread(self._read_file, thumbnail_path)
        response = await self.api_client.session.post(
            url,
            params={"videoId": video_id},
            headers=headers,
            content=data,
        )
        await self._maybe_await(response.raise_for_status())

    async def _maybe_await(self, value: Any) -> Any:
        if inspect.isawaitable(value):
            return await value
        return value

    def _read_file(self, path: str) -> bytes:
        with open(path, "rb") as f:
            return f.read()