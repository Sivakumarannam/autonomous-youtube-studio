import json
import time

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.upload_agent.agent import UploadAgent
from app.agents.upload_agent.models import UploadAgentOutput, UploadSettings
from app.core.config import settings as app_settings
from app.core.logging import get_logger
from app.database.models.agent_log import AgentLog, AgentLogLevel
from app.database.models.upload import Upload
from app.database.models.video import Video
from app.database.repositories.upload_repository import UploadRepository
from app.llm_providers.factory import get_llm_provider
from app.utils.retry import is_retryable_error

logger = get_logger(__name__)


class UploadAgentService:
    AGENT_NAME = "UploadAgent"

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def run_for_video(
        self,
        video_title: str,
        description: str = "",
        settings: UploadSettings | None = None,
        script_type: str = "long",
    ) -> UploadAgentOutput:
        """
        Prepare upload metadata using LLM.
        Kept for publishing_workflow compatibility — does not touch YouTube.
        """
        agent = UploadAgent(llm_provider=get_llm_provider())
        output = await agent.prepare_upload(
            video_title=video_title,
            description=description,
            settings=settings,
            script_type=script_type,
        )
        await self._log(
            AgentLogLevel.INFO,
            f"Upload prepared for {output.video_title}",
            context=json.dumps({"video_title": output.video_title, "status": output.status}),
            entity_id=None,
            execution_time=time.monotonic(),
        )
        return output

    async def run_upload_for_video(
        self,
        video: Video,
        upload: Upload,
        settings: UploadSettings | None = None,
        raise_on_error: bool = False,
    ) -> Upload:
        """
        Perform the actual YouTube upload for a completed Video.

        Steps:
        1. Validate credentials and video file presence.
        2. Use UploadAgent (LLM) to prepare optimised title / description / tags.
        3. Call YouTubeUploader via the existing httpx-based integration.
        4. Persist the result (PUBLISHED or FAILED) on the Upload record.

        raise_on_error
        ──────────────
        When False (default): all exceptions are caught internally; the Upload
        row is marked FAILED and returned.  Caller never sees an exception.

        When True: retryable exceptions (httpx timeouts, network errors,
        YouTube 429/5xx) are re-raised AFTER the internal catch so the caller
        (VideoPublishScheduler retry loop) can decide whether to retry.
        Non-retryable exceptions (missing credentials, missing file, YouTube
        auth/permission 4xx) are still caught and mark_failed'd, then returned.
        The session is NOT committed here; the caller is responsible for commit
        or rollback.  A rollback by the caller will undo the mark_uploading
        state change, restoring the Upload to its prior status — safe for retry.

        Brand-new upload session on every call
        ───────────────────────────────────────
        Each invocation creates fresh YouTubeAuthManager, YouTubeApiClient, and
        YouTubeUploader instances.  There is no resumable-session state carried
        between calls, so a stale or expired upload session from a previous
        failed attempt is never reused.
        """
        if settings is None:
            settings = UploadSettings()

        upload_repository = UploadRepository(self._session)

        if not all([
            app_settings.youtube_client_id,
            app_settings.youtube_client_secret,
            app_settings.youtube_refresh_token,
        ]):
            upload = await upload_repository.mark_failed(
                upload,
                "YouTube credentials not configured. "
                "Set YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET, and YOUTUBE_REFRESH_TOKEN.",
            )
            await self._log(
                AgentLogLevel.ERROR,
                "YouTube credentials not configured",
                entity_id=str(video.id),
                execution_time=time.monotonic(),
            )
            return upload

        if not video.video_path:
            upload = await upload_repository.mark_failed(
                upload, "Video record has no file path."
            )
            return upload

        import os
        if not os.path.exists(video.video_path):
            upload = await upload_repository.mark_failed(
                upload, f"Video file not found on disk: {video.video_path}"
            )
            return upload

        # Use LLM to optimise metadata
        agent = UploadAgent(llm_provider=get_llm_provider())
        title_hint = settings.title or upload.title or ""
        desc_hint = settings.description or upload.description or ""
        prepared = await agent.prepare_upload(
            video_title=title_hint,
            description=desc_hint,
            settings=settings,
        )

        final_title = prepared.video_title or title_hint or "Untitled Video"
        final_description = prepared.description or desc_hint or ""
        final_tags = prepared.tags or settings.tags or []
        final_privacy = upload.privacy_status or "private"

        upload = await upload_repository.mark_uploading(upload)

        _caught_exc: BaseException | None = None
        # Initialise to None so the finally block can safely check before close.
        _auth = None
        _client = None
        try:
            from app.integrations.youtube.auth import YouTubeAuthManager
            from app.integrations.youtube.client import YouTubeApiClient
            from app.integrations.youtube.uploader import YouTubeUploader

            # Fresh instances on every call — no stale resumable session state.
            _auth = YouTubeAuthManager(
                client_id=app_settings.youtube_client_id,
                client_secret=app_settings.youtube_client_secret,
                refresh_token=app_settings.youtube_refresh_token,
            )
            _client = YouTubeApiClient(auth_manager=_auth)
            uploader = YouTubeUploader(api_client=_client)

            # Resolve category: prefer per-upload override, then app default.
            final_category = (
                settings.category_id
                or getattr(app_settings, "youtube_category_id", "27")
            )
            metadata = await _client.create_video_metadata(
                title=final_title,
                description=final_description,
                tags=final_tags,
                category_id=final_category,
                privacy_status=final_privacy,
                notify_subscribers=settings.notify_subscribers,
                made_for_kids=settings.made_for_kids,
                ai_generated=settings.ai_generated,
            )

            logger.info(
                "Starting YouTube upload",
                video_id=str(video.id),
                title=final_title,
                privacy=final_privacy,
            )

            result = await uploader.upload_video(
                file_path=video.video_path,
                metadata=metadata,
            )

            youtube_video_id = result.get("id", "")
            youtube_url = (
                f"https://www.youtube.com/watch?v={youtube_video_id}"
                if youtube_video_id
                else ""
            )

            upload = await upload_repository.mark_published(
                upload,
                youtube_video_id=youtube_video_id,
                youtube_url=youtube_url,
                response_data=json.dumps(result),
            )

            upload = await upload_repository.update(
                upload,
                title=final_title,
                description=final_description,
                tags=json.dumps(final_tags),
            )

            # Auto-post an engagement comment right after upload. This is
            # a soft-fail step: the upload itself already succeeded above,
            # so a comment failure must never flip the upload to failed.
            # NOTE: the YouTube Data API has no endpoint to pin a comment
            # (confirmed against current API docs) — this only posts it;
            # pinning still requires one manual tap in Studio/the app.
            if youtube_video_id and prepared.pinned_comment:
                try:
                    await _client.post_top_level_comment(
                        video_id=youtube_video_id,
                        text=prepared.pinned_comment,
                    )
                    logger.info(
                        "Engagement comment posted (pin it manually in Studio)",
                        video_id=str(video.id),
                        youtube_video_id=youtube_video_id,
                    )
                except Exception as exc:
                    logger.warning(
                        "Could not auto-post engagement comment — upload still succeeded",
                        video_id=str(video.id),
                        error=str(exc),
                    )

            await self._log(
                AgentLogLevel.INFO,
                f"Video uploaded to YouTube: {youtube_url}",
                context=json.dumps({
                    "video_id": str(video.id),
                    "youtube_video_id": youtube_video_id,
                    "youtube_url": youtube_url,
                }),
                entity_id=str(video.id),
                execution_time=time.monotonic(),
            )

        except Exception as exc:
            _caught_exc = exc
            logger.error("YouTube upload failed", error=str(exc), video_id=str(video.id))
            upload = await upload_repository.mark_failed(upload, str(exc))
            await self._log(
                AgentLogLevel.ERROR,
                f"YouTube upload failed: {exc}",
                context=json.dumps({"video_id": str(video.id)}),
                entity_id=str(video.id),
                execution_time=time.monotonic(),
            )
        finally:
            # Always close HTTP connections regardless of success or failure so
            # retries start with a clean connection state (no stale socket).
            if _client is not None:
                try:
                    await _client.close()
                except Exception:
                    pass
            if _auth is not None:
                try:
                    await _auth.close()
                except Exception:
                    pass

        # Re-raise retryable exceptions when the caller (scheduler retry loop)
        # requested it.  The caller's rollback will undo mark_uploading,
        # returning the Upload to its pre-attempt status for a clean next try.
        if raise_on_error and _caught_exc is not None and is_retryable_error(_caught_exc):
            raise _caught_exc

        return upload

    async def _log(
        self,
        level: AgentLogLevel,
        message: str,
        context: str | None = None,
        entity_id: str | None = None,
        execution_time: float | None = None,
    ) -> None:
        entry = AgentLog(
            agent_name=self.AGENT_NAME,
            level=level,
            message=message,
            context=context,
            entity_type="video",
            entity_id=entity_id,
            execution_time=execution_time,
        )
        self._session.add(entry)
        await self._session.flush()