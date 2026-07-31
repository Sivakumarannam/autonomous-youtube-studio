"""YouTube-integration-specific exceptions.

Kept separate from app.core.exceptions so this can be raised/caught
precisely at the integration boundary without depending on (or risking
changes to) the app-wide exception hierarchy and its FastAPI handlers.
"""
from __future__ import annotations


class YouTubeVideoNotFoundError(Exception):
    """Raised when YouTube reports 404 videoNotFound on a delete attempt.

    This is an EXPECTED business scenario (the video was already removed
    directly on YouTube, outside this app) — not an application error.
    Callers should catch this specifically and prompt the user rather than
    surfacing a generic 500.
    """

    def __init__(self, video_id: str):
        self.video_id = video_id
        super().__init__(
            f"YouTube video {video_id} was not found — it has likely "
            f"already been deleted directly on YouTube."
        )