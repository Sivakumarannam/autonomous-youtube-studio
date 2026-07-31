"""Pipeline Agent Service.

Orchestrates: topic → script → quality gate → video render → upload record.
Does NOT call the YouTube upload directly — the Scheduler (Stage 3) handles
that once scheduled_at passes.

Each stage commits to DB so progress is visible while the pipeline is running.

Retry Manager — Surface A
─────────────────────────
Transient errors (httpx timeouts, network failures, YouTube 429/5xx) are
retried with exponential backoff up to max_retries on the PipelineRun row.
The backoff sequence is: base × 1, base × 2, base × 4 …
(base = settings.retry_base_backoff_seconds, default 30 s)

Non-retryable: QualityError, NotFoundError, YouTube auth/permission 4xx.

Idempotency: if pipeline_run.upload_id is already set when the upload-record
stage is (re-)entered, the existing Upload is reused instead of creating a
duplicate.

Retry state is scoped strictly to the PipelineRun row — every new run starts
at retry_count=0 regardless of history for the same topic/channel/video.
"""
from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import QualityError, NotFoundError
from app.core.logging import get_logger
from app.database.models.agent_log import AgentLog, AgentLogLevel
from app.database.models.pipeline_run import PipelineRun, PipelineStatus
from app.database.models.topic import TopicStatus
from app.database.models.upload import Upload, UploadStatus, PublishStatus
from app.database.models.video import VideoStatus
from app.database.repositories.pipeline_run_repository import PipelineRunRepository
from app.database.repositories.topic_repository import TopicRepository
from app.database.repositories.channel_repository import ChannelRepository
from app.agents.pipeline_agent.peak_scheduling import compute_scheduled_at
from app.database.repositories.upload_repository import UploadRepository
from app.database.repositories.video_repository import VideoRepository
from app.utils.retry import is_retryable_error

logger = get_logger(__name__)


class PipelineAgentService:
    """Runs the full topic→published pipeline for a PipelineRun record."""

    AGENT_NAME = "PipelineAgent"

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    async def run(self, pipeline_run: PipelineRun) -> None:
        """Execute all stages with retry-on-transient-failure.

        Outer retry loop: catches retryable exceptions from _execute_stages(),
        increments retry_count, sleeps with exponential backoff, then re-enters
        the stage sequence.  Non-retryable errors and exhausted retries cause an
        immediate FAILED transition.

        Does NOT re-raise; background-task-safe.
        """
        pipeline_repo = PipelineRunRepository(self._session)
        start = time.monotonic()

        # Track the original session so the finally block below can detect
        # whether _refresh_session() created a replacement.  The original is
        # owned and closed by the outer background-task context manager
        # (_run_pipeline_background's `async with session_factory() as session`);
        # any replacement session must be closed here explicitly.
        _original_session = self._session

        try:
            while True:
                try:
                    await self._execute_stages(pipeline_repo, pipeline_run, start)
                    return  # completed successfully

                except Exception as exc:
                    # Capture every pipeline_run attribute this block needs
                    # BEFORE rollback(): rollback() expires all ORM attributes
                    # by default, and the next access would need an implicit
                    # async refresh that can't happen from sync attribute
                    # access (raises sqlalchemy.exc.MissingGreenlet). This was
                    # invisible in unit tests that mock the session (rollback()
                    # is a no-op mock there, so nothing actually expires), but
                    # is a hard failure against a real AsyncSession.
                    run_id = pipeline_run.id
                    stage = pipeline_run.current_stage or "unknown"
                    max_retries = pipeline_run.max_retries
                    retry_count = pipeline_run.retry_count

                    # Rebuild pipeline_repo from the current self._session.
                    # _refresh_session() (called after a long video render) may
                    # have replaced self._session with a fresh pool checkout.
                    # If so, the pipeline_repo created at the top of run() is
                    # still bound to the old (now closed) session and will fail
                    # silently on any update/commit.  Always use self._session
                    # at the point of use in error handlers.
                    pipeline_repo = PipelineRunRepository(self._session)

                    await self._session.rollback()

                    # Re-fetch pipeline_run from the current session by its ID.
                    # We cannot call self._session.refresh(pipeline_run) here
                    # because after _refresh_session() the ORM instance may be
                    # associated with the old (now closed) session, not the
                    # current one.  A get_or_raise() loads a fresh identity-map
                    # entry bound to self._session regardless of which session
                    # originally loaded the object.
                    pipeline_run = await pipeline_repo.get_or_raise(run_id)

                    retryable = is_retryable_error(exc)
                    retries_left = max_retries - retry_count

                    if retryable and retries_left > 0:
                        # ── Transient failure: schedule a retry ──────────────
                        new_count = retry_count + 1
                        delay = settings.retry_base_backoff_seconds * (2 ** (new_count - 1))
                        next_retry_at = datetime.now(timezone.utc) + timedelta(seconds=delay)

                        logger.warning(
                            "Pipeline stage failed (retryable), backing off before retry.",
                            pipeline_run_id=str(run_id),
                            stage=stage,
                            retry_count=new_count,
                            max_retries=max_retries,
                            delay_seconds=delay,
                            error_type=type(exc).__name__,
                        )

                        try:
                            pipeline_run = await pipeline_repo.update(
                                pipeline_run,
                                retry_count=new_count,
                                next_retry_at=next_retry_at,
                                # Keep RUNNING so observers know it will resume.
                                status=PipelineStatus.RUNNING,
                                error_message=(
                                    f"Retry {new_count}/{max_retries} "
                                    f"after {type(exc).__name__} — retrying in {delay}s"
                                ),
                            )
                            await self._session.commit()
                            # Note: this app's session factory is configured
                            # with expire_on_commit=False, so — unlike
                            # rollback() above — commit() does not expire
                            # pipeline_run's attributes; no extra refresh needed
                            # here before the loop re-enters _execute_stages().
                        except Exception as _persist_exc:
                            logger.error(
                                "Failed to persist retry state — run may appear stuck.",
                                pipeline_run_id=str(run_id),
                                error=str(_persist_exc),
                            )

                        await asyncio.sleep(delay)
                        # Loop back → re-enter _execute_stages from the top.
                        # Rebuild pipeline_repo again at loop start so it uses
                        # self._session (which is always current after the sleep).
                        pipeline_repo = PipelineRunRepository(self._session)

                    else:
                        # ── Permanent failure: non-retryable or retries exhausted ──
                        if retryable:
                            err_msg = (
                                f"Max retries ({max_retries}) exhausted. "
                                f"Last error at '{stage}': "
                                f"{type(exc).__name__}: {str(exc)[:400]}"
                            )
                        else:
                            err_msg = f"{type(exc).__name__}: {str(exc)[:500]}"

                        logger.error(
                            "Pipeline failed permanently.",
                            pipeline_run_id=str(run_id),
                            stage=stage,
                            error=str(exc),
                            retryable=retryable,
                            retry_count=retry_count,
                        )

                        try:
                            pipeline_run = await pipeline_repo.update(
                                pipeline_run,
                                status=PipelineStatus.FAILED,
                                failed_stage=stage,
                                error_message=err_msg,
                                current_stage=None,
                            )
                            await self._session.commit()
                        except Exception as _persist_exc:
                            logger.error(
                                "Failed to persist FAILED status — run may appear stuck.",
                                pipeline_run_id=str(run_id),
                                error=str(_persist_exc),
                            )

                        # ── Notifications ───────────────────────────────────
                        try:
                            from app.notifications import notify
                            await notify(
                                title="Pipeline failed ❌",
                                body=f"Stage '{stage}' failed: {str(exc)[:200]}",
                                level="error",
                                extra={"Stage": stage, "Pipeline ID": str(run_id)},
                            )
                        except Exception:
                            pass
                        return

        finally:
            # If _refresh_session() swapped self._session for a fresh one,
            # close that replacement here.  The original session is owned
            # by the caller (_run_pipeline_background's context manager)
            # and must NOT be closed here — only close the replacement.
            if self._session is not _original_session:
                try:
                    await self._session.close()
                except Exception:
                    pass

    # ------------------------------------------------------------------
    # Stage execution body (extracted to keep run() readable)
    # ------------------------------------------------------------------

    async def _execute_stages(
        self,
        pipeline_repo: PipelineRunRepository,
        pipeline_run: PipelineRun,
        start: float,
    ) -> None:
        """Run all pipeline stages sequentially, committing after each.

        Raises any exception from individual stages so the retry loop in
        run() can classify and handle it.  Quality-gate failures are handled
        by returning early (not via exception) and are therefore not retried.
        """
        topic_repo = TopicRepository(self._session)
        video_repo = VideoRepository(self._session)
        upload_repo = UploadRepository(self._session)

        # ---------------------------------------------------------- #
        # STAGE: script                                                #
        # ---------------------------------------------------------- #
        pipeline_run = await pipeline_repo.update(
            pipeline_run,
            status=PipelineStatus.RUNNING,
            current_stage="script",
        )
        await self._session.commit()

        topic = await topic_repo.get_by_id_or_raise(pipeline_run.topic_id)

        # niche must come from the CHANNEL's niche field (e.g. "technology",
        # "music"), not topic.content_type — that field describes video
        # FORMAT (short/long/both), a completely different concept, and the
        # TopicAgent LLM is free to write "both" there. Using it as niche
        # previously produced garbage like "Follow for more both tips!" in
        # generated CTAs. Fetched here (rather than later, where it was
        # previously re-fetched for peak-time scheduling) so both uses share
        # one DB round trip and one consistent fallback path.
        channel_repo = ChannelRepository(self._session)
        try:
            channel = await channel_repo.get_by_id_or_raise(topic.channel_id)
            niche: str = channel.niche or "technology"
        except NotFoundError:
            logger.warning(
                "Channel not found while resolving niche; falling back to 'technology'.",
                channel_id=str(topic.channel_id),
            )
            channel = None
            niche = "technology"

        script = await self._generate_script(
            topic=topic,
            script_type=pipeline_run.script_type,
            niche=niche,
        )

        pipeline_run = await pipeline_repo.update(
            pipeline_run,
            script_id=script.id,
            current_stage="quality",
        )
        await self._session.commit()

        # ---------------------------------------------------------- #
        # STAGE: quality gate                                          #
        # ---------------------------------------------------------- #
        quality_passed = await self._run_quality_gate(script, niche)
        if not quality_passed:
            # QualityAgentService already set script.status=REJECTED;
            # pipeline halts here — quality failures are NOT retried.
            #
            # Also mark the Topic itself REJECTED (Phase 6): this is a
            # permanent failure, not a technical one, so the Topic must be
            # excluded from future automatic selection by the Daily
            # Automation Scheduler — tomorrow's tick picks a different
            # topic. automation_status is untouched here; only explicit
            # user action changes it.
            await topic_repo.update(topic, status=TopicStatus.REJECTED)
            pipeline_run = await pipeline_repo.update(
                pipeline_run,
                status=PipelineStatus.FAILED,
                failed_stage="quality",
                error_message="Script failed quality gate (score below threshold).",
                current_stage=None,
            )
            await self._session.commit()
            await self._log(
                AgentLogLevel.WARNING,
                "Pipeline halted: quality gate rejected the script.",
                context=json.dumps({"script_id": str(script.id)}),
                entity_id=str(pipeline_run.id),
                execution_time=time.monotonic() - start,
            )
            await self._session.commit()
            return

        # ---------------------------------------------------------- #
        # STAGE: SEO gate                                              #
        # ---------------------------------------------------------- #
        pipeline_run = await pipeline_repo.update(
            pipeline_run, current_stage="seo"
        )
        await self._session.commit()

        seo_passed = await self._run_seo_gate(script)
        if not seo_passed:
            # Pure rule-based check — no network call involved, so not
            # retryable.  Topic is rejected for the same reason as a
            # quality failure: a different topic must be chosen next run.
            await topic_repo.update(topic, status=TopicStatus.REJECTED)
            pipeline_run = await pipeline_repo.update(
                pipeline_run,
                status=PipelineStatus.FAILED,
                failed_stage="seo",
                error_message="Script failed SEO gate (score below threshold).",
                current_stage=None,
            )
            await self._session.commit()
            await self._log(
                AgentLogLevel.WARNING,
                "Pipeline halted: SEO gate rejected the script.",
                context=json.dumps({"script_id": str(script.id)}),
                entity_id=str(pipeline_run.id),
                execution_time=time.monotonic() - start,
            )
            await self._session.commit()
            return

        # ---------------------------------------------------------- #
        # STAGE: voice 
        # ---------------------------------------------------------- #
        # Force the voice stage to run unconditionally
        pipeline_run = await pipeline_repo.update(
            pipeline_run, current_stage="voice"
        )
        await self._session.commit()

        voice_passed = await self._run_voice_stage(script)
        if not voice_passed:
            await topic_repo.update(topic, status=TopicStatus.REJECTED)
            pipeline_run = await pipeline_repo.update(
                pipeline_run,
                status=PipelineStatus.FAILED,
                failed_stage="voice",
                error_message=(
                    "Voice generation did not produce a COMPLETE Voice "
                    "record after all local heal attempts."
                ),
                current_stage=None,
            )
            await self._session.commit()
            await self._log(
                AgentLogLevel.WARNING,
                "Pipeline halted: voice stage could not produce a COMPLETE Voice record.",
                context=json.dumps({"script_id": str(script.id)}),
                entity_id=str(pipeline_run.id),
                execution_time=time.monotonic() - start,
            )
            await self._session.commit()
            return

        # ---------------------------------------------------------- #
        # STAGE: video render                                          #
        # ---------------------------------------------------------- #
        pipeline_run = await pipeline_repo.update(
            pipeline_run, current_stage="video"
        )
        await self._session.commit()

        await self._render_video(script, topic, pipeline_run)

        # ── Refresh session after the long synchronous render ──────────────
        # The video renderer blocks the event loop for several minutes with
        # zero DB activity.  The remote DB (e.g. Neon) may have silently
        # dropped the asyncpg connection.  Close the stale session and open a
        # fresh one; pool_pre_ping then validates the next checkout.
        _run_id = pipeline_run.id
        await self._refresh_session()
        pipeline_repo = PipelineRunRepository(self._session)
        topic_repo = TopicRepository(self._session)
        video_repo = VideoRepository(self._session)
        upload_repo = UploadRepository(self._session)
        pipeline_run = await pipeline_repo.get_or_raise(_run_id)

        video = await video_repo.get_by_script_id(script.id)
        if video is None or video.status == VideoStatus.FAILED:
            error_msg = (
                (video.error_message if video else None)
                or "Video render failed with no error message."
            )
            pipeline_run = await pipeline_repo.update(
                pipeline_run,
                status=PipelineStatus.FAILED,
                failed_stage="video",
                error_message=error_msg,
                current_stage=None,
            )
            await self._session.commit()
            return

        pipeline_run = await pipeline_repo.update(
            pipeline_run,
            video_id=video.id,
            current_stage="upload",
        )
        await self._session.commit()

        # ---------------------------------------------------------- #
        # STAGE: create Upload record (no YouTube call yet)           #
        #                                                             #
        # Idempotency: on retry, pipeline_run.upload_id may already   #
        # be set from a prior attempt that succeeded in creating the  #
        # Upload before failing at a later point.  Reuse the existing #
        # record instead of creating a duplicate.                     #
        # ---------------------------------------------------------- #
        if pipeline_run.upload_id:
            upload = await upload_repo.get_or_raise(pipeline_run.upload_id)
            logger.info(
                "Pipeline retry: reusing existing Upload record (idempotency).",
                pipeline_run_id=str(pipeline_run.id),
                upload_id=str(upload.id),
            )
        else:
            tags: list[str] = []
            if script.seo_tags:
                try:
                    tags = json.loads(script.seo_tags)
                except Exception:
                    pass

            # Peak-engagement scheduling is best-effort: if the channel row
            # is missing/inconsistent, fail safe to the flat-delay behavior
            # rather than hard-failing the whole pipeline run over a
            # scheduling nicety.

            if channel is not None:
                scheduled_at = compute_scheduled_at(
                    channel=channel,
                    content_type=script.script_type.value
                    if hasattr(script.script_type, "value")
                    else str(script.script_type),
                    now_utc=datetime.now(timezone.utc),
                    flat_delay_minutes=settings.pipeline_publish_delay_minutes,
                )
            else:
                scheduled_at = datetime.now(timezone.utc) + timedelta(
                    minutes=settings.pipeline_publish_delay_minutes
                )

            upload = Upload(
                video_id=video.id,
                title=script.seo_title or topic.title,
                description=script.seo_description or topic.description or "",
                tags=json.dumps(tags),
                privacy_status="public",
                status=UploadStatus.SCHEDULED,
                publish_status=PublishStatus.DRAFT,
                scheduled_at=scheduled_at,
                max_retries=settings.scheduler_max_retries,
            )
            self._session.add(upload)
            await self._session.flush()
            await self._session.refresh(upload)

            # Auto-approve when enabled (default True).
            # Moves DRAFT → APPROVED → SCHEDULED.
            if settings.auto_publish_enabled:
                upload = await upload_repo.update(
                    upload, publish_status=PublishStatus.APPROVED
                )
                upload = await upload_repo.update(
                    upload, publish_status=PublishStatus.SCHEDULED
                )
            # If auto_publish_enabled=False the upload stays DRAFT and
            # a manual /api/v1/publishing/{id}/approve call is required.

            pipeline_run = await pipeline_repo.update(
                pipeline_run,
                upload_id=upload.id,
                current_stage="analytics",
            )
            await self._session.commit()

        # ---------------------------------------------------------- #
        # STAGE: analytics (deferred)                                 #
        # YouTube Analytics has ~24 h lag on freshly uploaded videos. #
        # The analytics endpoint can be polled manually later.        #
        # ---------------------------------------------------------- #
        pipeline_run = await pipeline_repo.update(
            pipeline_run, current_stage="analytics"
        )
        logger.info(
            "Analytics deferred — YouTube Analytics has ~24 h lag on new videos.",
            pipeline_run_id=str(pipeline_run.id),
            upload_id=str(upload.id),
        )

        # ---------------------------------------------------------- #
        # COMPLETE                                                     #
        # ---------------------------------------------------------- #
        # Mark the Topic PUBLISHED (Phase 6): a topic that already
        # succeeded must become ineligible for future automatic selection
        # by the Daily Automation Scheduler, or it could be picked again.
        await topic_repo.update(topic, status=TopicStatus.PUBLISHED)
        pipeline_run = await pipeline_repo.update(
            pipeline_run,
            status=PipelineStatus.COMPLETE,
            current_stage=None,
        )
        await self._session.commit()

        # ── Notifications ──────────────────────────────────────────────
        try:
            from app.notifications import notify
            await notify(
                title="Video pipeline complete ✅",
                body=f"Topic '{topic.title}' finished rendering and is queued for upload.",
                level="success",
                extra={
                    "Topic": topic.title,
                    "Script type": pipeline_run.script_type,
                    "Pipeline ID": str(pipeline_run.id),
                },
            )
        except Exception as _notify_exc:
            logger.warning("Notification failed (non-fatal)", error=str(_notify_exc))

        elapsed = time.monotonic() - start
        await self._log(
            AgentLogLevel.INFO,
            "Pipeline completed successfully.",
            context=json.dumps(
                {
                    "script_id": str(script.id),
                    "video_id": str(video.id),
                    "upload_id": str(upload.id),
                    "publish_status": upload.publish_status.value,
                    "retry_count": pipeline_run.retry_count,
                }
            ),
            entity_id=str(pipeline_run.id),
            execution_time=elapsed,
        )
        await self._session.commit()

    # ------------------------------------------------------------------
    # Private stage helpers
    # ------------------------------------------------------------------

    async def _generate_script(self, topic, script_type: str, niche: str):
        """Delegate to the appropriate script agent based on script_type."""
        if script_type == "short":
            from app.agents.short_script_agent.service import ShortScriptAgentService
            svc = ShortScriptAgentService(self._session)
        else:
            from app.agents.long_script_agent.service import LongScriptAgentService
            svc = LongScriptAgentService(self._session)
        return await svc.run_for_topic(topic, niche=niche)

    async def _run_seo_gate(self, script) -> bool:
        """Score the script's SEO metadata with the deterministic rule scorer.

        Writes the computed seo_gate_score back to the Script record, then
        returns True (pass) or False (fail).  Never retryable — the scorer
        makes no network calls.
        """
        from app.agents.seo_agent.scoring import score_seo_metadata
        from app.database.repositories.script_repository import ScriptRepository

        breakdown = score_seo_metadata(
            seo_title=script.seo_title,
            seo_description=script.seo_description,
            seo_tags_json=script.seo_tags,
            hashtags_json=script.hashtags,
        )

        script_repo = ScriptRepository(self._session)
        await script_repo.update(script, seo_gate_score=breakdown.total)
        await self._session.flush()

        logger.info(
            "SEO gate scored.",
            script_id=str(script.id),
            seo_gate_score=breakdown.total,
            seo_min_score=settings.seo_min_score,
            title_score=breakdown.title_score,
            description_score=breakdown.description_score,
            hashtag_score=breakdown.hashtag_score,
            tags_score=breakdown.tags_score,
            has_clickbait=breakdown.has_clickbait,
            has_cta=breakdown.has_cta,
            hashtag_count=breakdown.hashtag_count,
            tag_count=breakdown.tag_count,
        )

        return breakdown.total >= settings.seo_min_score

    async def _run_quality_gate(self, script, niche: str) -> bool:
        """Run the quality agent; return True on pass, False on fail."""
        from app.agents.quality_agent.service import QualityAgentService
        svc = QualityAgentService(self._session)
        try:
            await svc.run_for_script(script, niche=niche, raise_on_failure=True)
            return True
        except QualityError:
            return False

    async def _run_voice_stage(self, script) -> bool:
        """Run voice generation with local retry-on-incomplete-result healing.

        Calls VoiceAgentService.run_for_script() up to
        ``settings.voice_max_heal_attempts + 1`` times total (one initial
        attempt plus that many local heal retries). Between attempts sleeps
        briefly to avoid hammering whatever TTS/LLM service backs voice
        generation.

        Two independent, non-interacting failure modes:
        - Technical failures (exceptions from run_for_script) are NOT caught
          here — they propagate to the existing outer retry loop in run(),
          exactly like every other stage.
        - Artifact-incompleteness (run_for_script returns without raising,
          but the resulting Voice record is not status=COMPLETE) is healed
          locally via a plain Python counter that never touches
          PipelineRun.retry_count and never interacts with
          is_retryable_error().

        Returns True once a COMPLETE Voice record exists, False if local
        heal attempts are exhausted with the record still incomplete.
        """
        from app.agents.voice_agent.service import VoiceAgentService
        from app.database.models.voice import VoiceStatus
        from app.database.repositories.voice_repository import VoiceRepository

        svc = VoiceAgentService(self._session)
        voice_repo = VoiceRepository(self._session)

        max_attempts = settings.voice_max_heal_attempts + 1
        for attempt in range(max_attempts):
            await svc.run_for_script(script)
            await self._session.flush()

            voice = await voice_repo.get_by_script_id(script.id)
            if voice is not None and voice.status == VoiceStatus.COMPLETE:
                logger.info(
                    "Voice stage complete.",
                    script_id=str(script.id),
                    attempt=attempt,
                )
                return True

            logger.warning(
                "Voice record incomplete after generation attempt.",
                script_id=str(script.id),
                attempt=attempt,
                voice_status=voice.status.value if voice else None,
            )

            if attempt < max_attempts - 1:
                await asyncio.sleep(3)

        logger.error(
            "Voice stage exhausted local heal attempts; Voice record still incomplete.",
            script_id=str(script.id),
            voice_max_heal_attempts=settings.voice_max_heal_attempts,
        )
        return False

    async def _refresh_session(self) -> None:
        """Replace the held AsyncSession with a fresh pool checkout.

        Call after a long synchronous operation (e.g. video rendering) that
        blocked the event loop for several minutes with no DB activity.  The
        remote DB (Neon, RDS, etc.) may have silently closed the idle asyncpg
        connection; pool_pre_ping only validates at *checkout* time, so a
        connection already checked out is not re-validated.  Closing the old
        session returns it to the pool and the next operation gets a fresh,
        pre-ping-validated connection.
        """
        from app.database.connection import get_session_factory as _gsf
        await self._session.close()
        self._session = _gsf()()

    async def _render_video(self, script, topic, pipeline_run: PipelineRun) -> None:
        """Delegate to VideoAgentService.run_for_script (creates the Video row)."""
        from app.agents.video_agent.service import VideoAgentService
        svc = VideoAgentService(self._session)
        await svc.run_for_script(
            script=script,
            topic_title=script.seo_title or topic.title or "",
            description=script.seo_description or topic.description or "",
            script_type=pipeline_run.script_type,
        )

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
            entity_type="pipeline_run",
            entity_id=entity_id,
            execution_time=execution_time,
        )
        self._session.add(entry)
        await self._session.flush()