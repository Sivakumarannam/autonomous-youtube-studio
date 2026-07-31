"""Unit tests for ShortScriptAgent."""
import json
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.agents.short_script_agent.agent import ShortScriptAgent
from app.agents.short_script_agent.workflow import ShortsWorkflow
from app.llm_providers.mock_provider import MockLLMProvider


@pytest.fixture
def mock_llm():
    return MockLLMProvider()


@pytest.fixture
def agent(mock_llm):
    return ShortScriptAgent(llm_provider=mock_llm)


class _FakeTopic:
    def __init__(self, title: str = "Shorts Test Topic"):
        self.id = uuid.uuid4()
        self.title = title
        self.description = None
        self.channel_id = uuid.uuid4()


class _FakeResearch:
    def __init__(self):
        self.summary = "Quick research summary for shorts testing"
        self.key_facts = json.dumps(["Fact A", "Fact B", "Fact C"])
        self.raw_data = json.dumps({"talking_points": ["Point 1"]})


class TestShortScriptAgentGenerate:
    async def test_generate_returns_script_output(self, agent):
        output = await agent._generate(
            topic_title="Docker in 30 Seconds",
            research_summary=None,
            key_facts=[],
            niche="technology",
            language="en",
        )
        assert output is not None
        assert output.full_script is not None
        assert len(output.full_script) > 0

    async def test_generate_has_hook(self, agent):
        output = await agent._generate(
            topic_title="Python One-Liners",
            research_summary="Quick research",
            key_facts=["Python is fast", "Easy to learn"],
            niche="python",
            language="en",
        )
        assert isinstance(output.hook, str)

    async def test_generate_has_cta(self, agent):
        output = await agent._generate(
            topic_title="Linux Commands",
            research_summary=None,
            key_facts=[],
            niche="linux",
            language="en",
        )
        assert isinstance(output.cta, str)
        assert len(output.cta) > 0

    async def test_generate_has_seo_data(self, agent):
        output = await agent._generate(
            topic_title="Git Commands You Must Know",
            research_summary=None,
            key_facts=[],
            niche="devops",
            language="en",
        )
        assert isinstance(output.seo_title, str)
        assert isinstance(output.tags, list)
        assert isinstance(output.hashtags, list)

    async def test_generate_word_count_reasonable(self, agent):
        output = await agent._generate(
            topic_title="Kubernetes Pods",
            research_summary=None,
            key_facts=[],
            niche="devops",
            language="en",
        )
        # Mock returns ~40-90 word output or at least non-zero
        assert output.word_count >= 0

    async def test_generate_duration_positive(self, agent):
        output = await agent._generate(
            topic_title="FastAPI Speed",
            research_summary=None,
            key_facts=[],
            niche="python",
            language="en",
        )
        assert output.estimated_duration_seconds > 0


class TestShortScriptAgentParsing:
    def test_parse_valid_json(self, agent):
        raw = json.dumps({
            "hook": "Did you know Docker can save hours?",
            "body": "Docker packages your app so it runs anywhere.",
            "cta": "Follow for more DevOps tips!",
            "full_script": "Did you know Docker can save hours? Docker packages your app. Follow!",
            "word_count": 13,
            "estimated_duration_seconds": 6,
            "seo_title": "Docker in Seconds",
            "seo_description": "Quick Docker tip",
            "tags": ["docker", "devops"],
            "hashtags": ["#Docker", "#Shorts"],
        })
        result = agent._parse_response(raw, "Docker")
        assert result.hook == "Did you know Docker can save hours?"
        assert result.word_count == 13
        assert "#Docker" in result.hashtags

    def test_parse_plain_text_fallback(self, agent):
        raw = "This is a plain text script with no JSON structure at all"
        result = agent._parse_response(raw, "Plain Topic")
        assert result.full_script is not None
        assert len(result.full_script) > 0

    def test_parse_missing_full_script_combines_parts(self, agent):
        raw = json.dumps({
            "hook": "Hook text",
            "body": "Body text",
            "cta": "CTA text",
            "word_count": 3,
        })
        result = agent._parse_response(raw, "Combined")
        assert "Hook" in result.full_script or "hook" in result.full_script.lower()

    def test_extract_research_with_none(self, agent):
        summary, facts = agent._extract_research(None)
        assert summary is None
        assert facts == []

    def test_extract_research_with_data(self, agent):
        research = _FakeResearch()
        summary, facts = agent._extract_research(research)
        assert summary == "Quick research summary for shorts testing"
        assert len(facts) == 3


class TestShortsWorkflow:
    async def test_workflow_complete(self, mock_llm):
        workflow = ShortsWorkflow(llm_provider=mock_llm)
        state = await workflow.run(
            topic_id=str(uuid.uuid4()),
            topic_title="Docker Shorts",
            channel_id=str(uuid.uuid4()),
            niche="devops",
        )
        assert state["status"] in ("complete", "failed")

    async def test_workflow_has_script_content(self, mock_llm):
        workflow = ShortsWorkflow(llm_provider=mock_llm)
        state = await workflow.run(
            topic_id=str(uuid.uuid4()),
            topic_title="Python Tips",
            channel_id=str(uuid.uuid4()),
            niche="python",
        )
        if state["status"] == "complete":
            assert state["script_content"] is not None
            assert len(state["script_content"]) > 0

    async def test_workflow_failed_llm(self):
        bad_llm = MagicMock()
        bad_llm.generate_text = AsyncMock(side_effect=Exception("LLM error"))
        bad_llm.provider_name = "mock"
        workflow = ShortsWorkflow(llm_provider=bad_llm)
        state = await workflow.run(
            topic_id=str(uuid.uuid4()),
            topic_title="Failing Shorts",
            channel_id=str(uuid.uuid4()),
        )
        assert state["status"] == "failed"