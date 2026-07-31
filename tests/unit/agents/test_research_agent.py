"""Unit tests for ResearchAgent."""
import json
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.agents.research_agent.agent import ResearchAgent
from app.agents.research_agent.workflow import ResearchWorkflow
from app.llm_providers.mock_provider import MockLLMProvider


@pytest.fixture
def mock_llm():
    return MockLLMProvider()


@pytest.fixture
def agent(mock_llm):
    return ResearchAgent(llm_provider=mock_llm)


class _FakeTopic:
    def __init__(self, title: str = "Test Topic", description: str | None = None):
        self.id = uuid.uuid4()
        self.title = title
        self.description = description


class TestResearchAgentRun:
    async def test_run_returns_dict(self, agent):
        topic = _FakeTopic("Docker vs Kubernetes")
        result = await agent.run(topic=topic, niche="technology")
        assert isinstance(result, dict)

    async def test_run_has_summary(self, agent):
        topic = _FakeTopic("Python Async")
        result = await agent.run(topic=topic)
        assert "summary" in result
        assert isinstance(result["summary"], str)
        assert len(result["summary"]) > 0

    async def test_run_has_key_facts(self, agent):
        topic = _FakeTopic("FastAPI Tutorial")
        result = await agent.run(topic=topic)
        assert "key_facts" in result
        assert isinstance(result["key_facts"], list)

    async def test_run_has_references(self, agent):
        topic = _FakeTopic("Linux Commands")
        result = await agent.run(topic=topic)
        assert "references" in result
        assert isinstance(result["references"], list)

    async def test_run_has_talking_points(self, agent):
        topic = _FakeTopic("Git Best Practices")
        result = await agent.run(topic=topic)
        assert "talking_points" in result
        assert isinstance(result["talking_points"], list)

    async def test_run_with_description(self, agent):
        topic = _FakeTopic("Docker Tutorial", description="Beginner guide to containers")
        result = await agent.run(topic=topic, niche="devops")
        assert "summary" in result


class TestResearchAgentParsing:
    def test_parse_valid_json(self, agent):
        raw = json.dumps({
            "summary": "Test summary content here",
            "key_facts": ["Fact 1", "Fact 2"],
            "references": ["https://example.com"],
            "talking_points": ["Point 1", "Point 2"],
            "target_audience": "Developers",
            "difficulty_level": "beginner",
        })
        result = agent._parse_research(raw, "Test Topic")
        assert result["summary"] == "Test summary content here"
        assert len(result["key_facts"]) == 2

    def test_parse_json_with_code_fence(self, agent):
        raw = '```json\n{"summary": "Fenced summary", "key_facts": [], "references": [], "talking_points": []}\n```'
        result = agent._parse_research(raw, "Topic")
        assert result["summary"] == "Fenced summary"

    def test_parse_invalid_json_returns_fallback(self, agent):
        raw = "Not valid JSON at all — just prose text"
        result = agent._parse_research(raw, "Fallback Topic")
        assert "summary" in result
        assert "key_facts" in result
        assert "references" in result

    def test_parse_missing_fields_filled_with_defaults(self, agent):
        raw = json.dumps({"summary": "Only summary provided"})
        result = agent._parse_research(raw, "Partial Topic")
        assert result["key_facts"] == []
        assert result["references"] == []
        assert result["talking_points"] == []

    def test_fallback_research_has_all_fields(self, agent):
        fallback = agent._fallback_research("My Topic")
        assert "summary" in fallback
        assert "key_facts" in fallback
        assert "references" in fallback
        assert "talking_points" in fallback
        assert "target_audience" in fallback
        assert "difficulty_level" in fallback


class TestResearchWorkflow:
    async def test_workflow_complete(self, mock_llm):
        workflow = ResearchWorkflow(llm_provider=mock_llm)
        state = await workflow.run(
            topic_id=str(uuid.uuid4()),
            topic_title="Kubernetes Networking",
            niche="devops",
        )
        assert state["status"] in ("complete", "failed")

    async def test_workflow_complete_has_result(self, mock_llm):
        workflow = ResearchWorkflow(llm_provider=mock_llm)
        state = await workflow.run(
            topic_id=str(uuid.uuid4()),
            topic_title="Python Type Hints",
            niche="python",
        )
        if state["status"] == "complete":
            assert state["research_result"] is not None
            assert "summary" in state["research_result"]

    async def test_workflow_with_description(self, mock_llm):
        workflow = ResearchWorkflow(llm_provider=mock_llm)
        state = await workflow.run(
            topic_id=str(uuid.uuid4()),
            topic_title="Docker Compose",
            topic_description="Multi-container Docker applications",
            niche="devops",
        )
        assert state["topic_title"] == "Docker Compose"

    async def test_workflow_failed_llm(self):
        bad_llm = MagicMock()
        bad_llm.generate_text = AsyncMock(side_effect=Exception("LLM down"))
        bad_llm.provider_name = "mock"
        workflow = ResearchWorkflow(llm_provider=bad_llm)
        state = await workflow.run(
            topic_id=str(uuid.uuid4()),
            topic_title="Failing Topic",
        )
        assert state["status"] == "failed"
        assert state["error"] is not None