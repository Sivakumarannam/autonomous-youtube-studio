"""End-to-end integration tests for PipelineAgentService.run().

Unlike the per-stage unit tests, these tests exercise the pipeline as a
whole: real DB-backed Channel/Topic rows (in-memory SQLite via the shared
`test_session` fixture), the real ShortScriptAgent/LongScriptAgent →
QualityAgent → SEO scorer → VoiceAgent chain running against
MockLLMProvider, and only the genuinely-external pieces (video rendering —
ffmpeg/MoviePy — and scene-image generation — Pollinations over HTTP)
patched out, per the project's "no real network calls" testing convention
(see tests/unit/agents/test_video_agent.py for the equivalent boundary on
video work).

Test-data note
--------------
MockLLMProvider._select_response (app/llm_providers/mock_provider.py) picks
a canned response by scanning the prompt text for keyword buckets in a
fixed order, checking for "topic" first. Every agent prompt in this app
legitimately embeds the topic's title (e.g. `for: "{topic_title}"`), and
test topic titles contain the literal word "Topic" — so in practice nearly
every prompt (script generation, quality review, ...) matches the "topic"
bucket before it can ever reach its own intended bucket ("short script" /
"long script" / "quality" / ...), and falls back to a topics-list JSON
that the receiving parser can't use, cascading into empty SEO metadata
and/or a failing quality score. That's a pre-existing routing ambiguity in
the shared canned-response lookup table (fine for its own callers, who
don't care about exact response shape), not a pipeline defect, so instead
of relying on prompt-keyword sniffing this module keys canned responses
off each agent's distinctive `system` prompt string — the agents' own
generation/parsing code and the pipeline code are exercised unmodified.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import httpx
import pytest

from app.agents.pipeline_agent.service import PipelineAgentService
from app.agents.video_agent.renderer import VideoRenderResult
from app.core.config import settings
from app.database.models.pipeline_run import PipelineRun, PipelineStatus
from app.database.models.upload import PublishStatus, UploadStatus
from app.database.models.video import VideoStatus
from app.database.models.voice import VoiceStatus
from app.database.repositories.script_repository import ScriptRepository
from app.database.repositories.upload_repository import UploadRepository
from app.database.repositories.video_repository import VideoRepository
from app.database.repositories.voice_repository import VoiceRepository
from app.agents.quality_agent.prompts import QUALITY_SYSTEM_PROMPT
from app.agents.short_script_agent.prompts import SHORT_SCRIPT_SYSTEM_PROMPT
from app.agents.long_script_agent.prompts import LONG_SCRIPT_SYSTEM_PROMPT
from app.llm_providers import factory as llm_factory
from app.llm_providers.mock_provider import MOCK_RESPONSES, MockLLMProvider

from tests.conftest import create_test_channel, create_test_topic

pytestmark = pytest.mark.asyncio

# ---------------------------------------------------------------------------
# JSON script payloads that satisfy the SEO gate (title 60-70 chars, no
# clickbait, a tag keyword present in the title, a CTA + >=100 char
# description, >=7 inline #hashtags, 20-28 seo_tags) — see
# app/agents/seo_agent/scoring.py for the exact thresholds.
# ---------------------------------------------------------------------------

_SEO_TITLE = "Docker vs Kubernetes: The Ultimate DevOps Comparison Guide 2026"
_SEO_DESCRIPTION = (
    "Discover the definitive comparison between Docker and Kubernetes in this "
    "deep dive. Subscribe for more DevOps tutorials! "
    "#Docker #Kubernetes #DevOps #CloudNative #Containers #Programming #Tech #Tutorial"
)
_SEO_TAGS = [f"devops-tag-{i}" for i in range(22)]
_SEO_HASHTAGS = ["#Docker", "#Kubernetes", "#DevOps"]

_SHORT_SCRIPT_JSON = json.dumps(
    {
        "hook": "Did you know Docker and Kubernetes are NOT the same thing?",
        "body": "Docker creates containers. Kubernetes orchestrates them at scale.",
        "cta": "Follow for more DevOps tips!",
        "full_script": (
            "Did you know Docker and Kubernetes are NOT the same thing? "
            "Docker creates containers. Kubernetes orchestrates them at scale. "
            "Follow for more DevOps tips!"
        ),
        "word_count": 60,
        "estimated_duration_seconds": 26,
        "seo_title": _SEO_TITLE,
        "seo_description": _SEO_DESCRIPTION,
        "tags": _SEO_TAGS,
        "hashtags": _SEO_HASHTAGS,
    }
)

_LONG_SCRIPT_JSON = json.dumps(
    {
        "introduction": "Welcome back to the channel! Today: Docker vs Kubernetes.",
        "sections": [
            {"title": "What is Docker?", "content": "Docker packages apps into containers.", "duration_seconds": 120},
            {"title": "What is Kubernetes?", "content": "Kubernetes orchestrates containers at scale.", "duration_seconds": 120},
        ],
        "conclusion": "Docker and Kubernetes are complementary, not competing.",
        "cta": "Like, subscribe, and comment below!",
        "full_script": (
            "Welcome back to the channel! Today: Docker vs Kubernetes. "
            "Docker packages apps into containers. Kubernetes orchestrates "
            "containers at scale. Docker and Kubernetes are complementary, "
            "not competing. Like, subscribe, and comment below!"
        ),
        "word_count": 1200,
        "estimated_duration_seconds": 540,
        "hook": "Docker vs Kubernetes: settled once and for all.",
        "seo_title": _SEO_TITLE,
        "seo_description": _SEO_DESCRIPTION,
        "tags": _SEO_TAGS,
        "hashtags": _SEO_HASHTAGS,
        "thumbnail_concept": "Split screen: Docker whale vs Kubernetes helm.",
    }
)


@pytest.fixture(autouse=True)
def _use_mock_llm_provider(monkeypatch):
    """Route get_llm_provider() to MockLLMProvider for the whole test module."""
    monkeypatch.setattr(settings, "llm_provider", "mock")
    llm_factory.reset_llm_provider()
    yield
    llm_factory.reset_llm_provider()


@pytest.fixture(autouse=True)
def _deterministic_agent_responses(monkeypatch):
    """Key canned LLM responses off each agent's `system` prompt.

    See module docstring: prompt-keyword sniffing in
    MockLLMProvider._select_response is unreliable for these prompts because
    they all embed a topic title containing the word "topic". Script
    generation gets SEO-gate-passing metadata; QualityAgent gets a
    guaranteed-passing score. Every other prompt (voice pre-processing,
    video plan) still goes through the real keyword-based selection
    unchanged.
    """
    real_generate_text = MockLLMProvider.generate_text

    async def _generate_text(self, prompt, system=None, temperature=0.7, max_tokens=4096):
        if system == SHORT_SCRIPT_SYSTEM_PROMPT:
            return _SHORT_SCRIPT_JSON
        if system == LONG_SCRIPT_SYSTEM_PROMPT:
            return _LONG_SCRIPT_JSON
        if system == QUALITY_SYSTEM_PROMPT:
            return MOCK_RESPONSES["quality"]
        return await real_generate_text(self, prompt, system=system, temperature=temperature, max_tokens=max_tokens)

    monkeypatch.setattr(MockLLMProvider, "generate_text", _generate_text)
    yield


@pytest.fixture(autouse=True)
def _stub_video_rendering(monkeypatch):
    """Avoid real ffmpeg/MoviePy rendering and real Pollinations image calls.

    Per tests/unit/agents/test_video_agent.py convention: LLM planning goes
    through MockLLMProvider like everything else, but actual media rendering
    and outbound HTTP for scene images are stubbed so the suite stays fast,
    deterministic, and network-free.
    """

    def _fake_render(self, script_id, scenes, audio_path, script_type="long", image_paths=None):
        return VideoRenderResult(
            success=True,
            video_path=f"storage/videos/{script_id}.mp4",
            duration_seconds=30.0,
            file_size=1024,
        )

    monkeypatch.setattr(
        "app.agents.video_agent.renderer.VideoRenderer.render", _fake_render
    )
    monkeypatch.setattr(
        "app.integrations.image_provider.ImageProvider.generate",
        AsyncMock(return_value=None),
    )
    yield


async def _make_pipeline_run(session, *, script_type: str = "long", voice_enabled: bool = False, **channel_kwargs):
    """Build a Channel + Topic + PipelineRun row ready for .run()."""
    channel = await create_test_channel(session, **channel_kwargs)
    topic = await create_test_topic(
        session,
        channel_id=channel.id,
        content_type="technology",
    )
    pipeline_run = PipelineRun(
        topic_id=topic.id,
        channel_id=channel.id,
        script_type=script_type,
        status=PipelineStatus.PENDING,
        max_retries=3,
    )
    session.add(pipeline_run)
    await session.flush()
    await session.refresh(pipeline_run)
    return channel, topic, pipeline_run


# ---------------------------------------------------------------------------
# Test 1: full success, voice stage enabled end-to-end
# ---------------------------------------------------------------------------

async def test_full_pipeline_success_with_voice_and_peak_scheduling(test_session, monkeypatch):
    monkeypatch.setattr(settings, "voice_enabled", True)

    channel, topic, pipeline_run = await _make_pipeline_run(
        test_session, script_type="long"
    )

    from app.agents.pipeline_agent.peak_scheduling import compute_scheduled_at as real_compute

    captured: dict[str, object] = {}

    def _spy_compute(**kwargs):
        result = real_compute(**kwargs)
        captured["kwargs"] = kwargs
        captured["result"] = result
        return result

    with patch(
        "app.agents.pipeline_agent.service.compute_scheduled_at",
        side_effect=_spy_compute,
    ) as spy_compute:
        await PipelineAgentService(test_session).run(pipeline_run)

    await test_session.refresh(pipeline_run)
    assert pipeline_run.status == PipelineStatus.COMPLETE
    assert pipeline_run.failed_stage is None
    assert pipeline_run.current_stage is None
    assert pipeline_run.script_id is not None
    assert pipeline_run.video_id is not None
    assert pipeline_run.upload_id is not None

    # Peak-engagement scheduling actually ran (not just a flat delay) —
    # assert the pipeline called through to the real scheduling function
    # with this run's channel and script type, and used its return value.
    spy_compute.assert_called_once()
    assert captured["kwargs"]["channel"].id == channel.id
    assert captured["kwargs"]["content_type"] == "long"

    script_repo = ScriptRepository(test_session)
    voice_repo = VoiceRepository(test_session)
    video_repo = VideoRepository(test_session)
    upload_repo = UploadRepository(test_session)

    script = await script_repo.get_by_id_or_raise(pipeline_run.script_id)
    # Both gates ran for real and recorded their scores on the Script row —
    # not just "the pipeline didn't halt".
    assert script.quality_score >= 85
    assert script.seo_gate_score >= 60

    voice = await voice_repo.get_by_script_id(pipeline_run.script_id)
    assert voice is not None
    assert voice.status == VoiceStatus.COMPLETE

    video = await video_repo.get_by_script_id(pipeline_run.script_id)
    assert video is not None
    assert video.status == VideoStatus.COMPLETE
    assert video.id == pipeline_run.video_id

    upload = await upload_repo.get_or_raise(pipeline_run.upload_id)
    # Cross-artifact consistency: the Upload's video_id must point at the
    # exact Video row created in this same run.
    assert upload.video_id == video.id
    assert upload.status == UploadStatus.SCHEDULED
    assert upload.publish_status == PublishStatus.SCHEDULED
    # SQLite round-trips datetimes as naive, so compare on timestamp value
    # rather than tz-aware equality.
    expected_scheduled_at: datetime = captured["result"]  # type: ignore[assignment]
    assert upload.scheduled_at.replace(tzinfo=timezone.utc) == expected_scheduled_at
    assert expected_scheduled_at > datetime.now(timezone.utc)

    await test_session.refresh(topic)
    assert topic.status.value == "published"


# ---------------------------------------------------------------------------
# Test 2: SEO gate rejection halts the pipeline before video/upload
# ---------------------------------------------------------------------------

async def test_seo_gate_failure_halts_before_video_and_upload(test_session, monkeypatch):
    # Force the SEO gate to fail deterministically without touching the
    # rule-based scorer itself — the scorer is pure and already covered by
    # its own unit tests; here we only need *a* script that fails it, so
    # override this test's script response to plain (non-JSON) text, which
    # ShortScriptAgent._parse_response falls back to near-empty SEO fields
    # for (tags=[], hashtags=["#Shorts"]).
    real_generate_text = MockLLMProvider.generate_text

    async def _plain_text_script(self, prompt, system=None, temperature=0.7, max_tokens=4096):
        if system == SHORT_SCRIPT_SYSTEM_PROMPT:
            return "Just a plain-text script with no SEO metadata at all."
        return await real_generate_text(self, prompt, system=system, temperature=temperature, max_tokens=max_tokens)

    monkeypatch.setattr(MockLLMProvider, "generate_text", _plain_text_script)

    channel, topic, pipeline_run = await _make_pipeline_run(
        test_session, script_type="short"
    )

    with patch(
        "app.agents.video_agent.service.VideoAgentService.run_for_script",
        new_callable=AsyncMock,
    ) as video_mock:
        await PipelineAgentService(test_session).run(pipeline_run)

    video_mock.assert_not_called()

    await test_session.refresh(pipeline_run)
    assert pipeline_run.status == PipelineStatus.FAILED
    assert pipeline_run.failed_stage == "seo"
    assert pipeline_run.current_stage is None
    assert pipeline_run.script_id is not None
    assert pipeline_run.video_id is None
    assert pipeline_run.upload_id is None

    await test_session.refresh(topic)
    assert topic.status.value == "rejected"

    video_repo = VideoRepository(test_session)
    video = await video_repo.get_by_script_id(pipeline_run.script_id)
    assert video is None


# ---------------------------------------------------------------------------
# Test 3: voice stage exhausts local heal attempts -> video never rendered
# ---------------------------------------------------------------------------

async def test_voice_stage_failure_halts_before_video(test_session, monkeypatch):
    monkeypatch.setattr(settings, "voice_enabled", True)
    monkeypatch.setattr(settings, "voice_max_heal_attempts", 0)

    channel, topic, pipeline_run = await _make_pipeline_run(
        test_session, script_type="long"
    )

    async def _leave_incomplete(self, script, voice_settings=None):
        # Simulate a Voice record that never reaches COMPLETE, without
        # raising — this is the "artifact incompleteness" path, distinct
        # from a technical exception.
        from app.database.models.voice import Voice, VoiceProvider

        from app.database.repositories.voice_repository import VoiceRepository

        voice_repo = VoiceRepository(self._session)
        existing = await voice_repo.get_by_script_id(script.id)
        if existing is None:
            voice = Voice(
                script_id=script.id,
                provider=VoiceProvider.MOCK,
                status=VoiceStatus.FAILED,
                error_message="Simulated incomplete synthesis.",
            )
            self._session.add(voice)
            await self._session.flush()
        return None

    with patch(
        "app.agents.voice_agent.service.VoiceAgentService.run_for_script",
        new=_leave_incomplete,
    ), patch(
        "app.agents.video_agent.service.VideoAgentService.run_for_script",
        new_callable=AsyncMock,
    ) as video_mock:
        await PipelineAgentService(test_session).run(pipeline_run)

    video_mock.assert_not_called()

    await test_session.refresh(pipeline_run)
    assert pipeline_run.status == PipelineStatus.FAILED
    assert pipeline_run.failed_stage == "voice"
    assert pipeline_run.video_id is None
    assert pipeline_run.upload_id is None

    await test_session.refresh(topic)
    assert topic.status.value == "rejected"


# ---------------------------------------------------------------------------
# Test 4: transient failure during script generation retries and recovers
# ---------------------------------------------------------------------------

async def test_transient_script_failure_retries_and_recovers(test_session, monkeypatch):
    monkeypatch.setattr(settings, "retry_base_backoff_seconds", 0)

    channel, topic, pipeline_run = await _make_pipeline_run(
        test_session, script_type="long"
    )

    from app.llm_providers.mock_provider import MockLLMProvider

    real_generate_text = MockLLMProvider.generate_text
    call_count = {"n": 0}

    async def _flaky_generate_text(self, prompt, system=None, temperature=0.7, max_tokens=4096):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise httpx.TimeoutException("simulated transient timeout")
        return await real_generate_text(self, prompt, system=system, temperature=temperature, max_tokens=max_tokens)

    with patch.object(
        MockLLMProvider, "generate_text", new=_flaky_generate_text
    ):
        await PipelineAgentService(test_session).run(pipeline_run)

    # The very first LLM call (script generation) failed once, then the
    # outer retry loop backed off (base backoff forced to 0s above) and
    # re-entered the stage sequence from the top, and the second attempt
    # succeeded.
    assert call_count["n"] >= 2

    await test_session.refresh(pipeline_run)
    assert pipeline_run.status == PipelineStatus.COMPLETE
    assert pipeline_run.retry_count == 1
    assert pipeline_run.failed_stage is None
    assert pipeline_run.script_id is not None
    assert pipeline_run.video_id is not None
    assert pipeline_run.upload_id is not None

    await test_session.refresh(topic)
    assert topic.status.value == "published"
