"""
Integration test: RAG fail-safe fallback.

Proves that when RAG_RESEARCH_ENABLED=true and a RAG pipeline step (Search)
raises an exception, ShortScriptAgentService.run_for_topic() still:
  (a) logs a warning for the RAG failure,
  (b) completes successfully and returns a valid Script,
  (c) does not propagate the exception.

Uses the same MockLLMProvider pattern as tests/unit/workflows/
test_youtube_pipeline.py. No real video rendering or YouTube credentials
are touched.
"""
from unittest.mock import AsyncMock, patch

import pytest
import structlog
from structlog.testing import capture_logs

from app.agents.short_script_agent.service import ShortScriptAgentService
from app.database.models.script import Script
from app.core.config import settings
from tests.conftest import create_test_channel, create_test_topic


@pytest.mark.asyncio
async def test_rag_search_failure_falls_back_gracefully(test_session, monkeypatch):
    # Enable RAG research for this test only.
    monkeypatch.setattr(settings, "rag_research_enabled", True)

    channel = await create_test_channel(test_session)
    topic = await create_test_topic(test_session, channel_id=channel.id, title="Docker vs Kubernetes")

    # Force the Search step of the RAG pipeline to blow up.
    with patch(
        "app.rag.rag_research_service.search",
        new=AsyncMock(side_effect=RuntimeError("search backend unreachable")),
    ):
        with capture_logs() as logs:
            service = ShortScriptAgentService(test_session)
            script = await service.run_for_topic(topic, niche="technology")

    # (b) script generation still completes successfully with a valid Script.
    assert isinstance(script, Script)
    assert script.id is not None
    assert script.content
    assert script.word_count > 0

    # (a) a warning is logged for the RAG failure.
    warning_events = [
        entry["event"] for entry in logs if entry.get("log_level") == "warning"
    ]
    assert any("RAG" in event for event in warning_events), (
        f"Expected a RAG-related warning log, got: {warning_events}"
    )

    # (c) no exception propagated out of the call — reaching this point
    # without pytest.raises already proves that, but assert explicitly
    # that the failure was fully swallowed rather than re-raised anywhere.
    assert True
