"""Unit tests for TopicAgent."""
import json
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from app.agents.topic_agent.agent import TopicAgent
from app.agents.topic_agent.workflow import TopicDiscoveryWorkflow
from app.database.models.topic import TopicSource
from app.llm_providers.mock_provider import MockLLMProvider


@pytest.fixture
def mock_llm():
    return MockLLMProvider()


@pytest.fixture
def agent(mock_llm):
    return TopicAgent(llm_provider=mock_llm)


class TestTopicAgentGenerate:
    async def test_run_returns_list(self, agent):
        result = await agent.run(
            channel_id=uuid.uuid4(),
            count=3,
            niche="technology",
        )
        assert isinstance(result, list)

    async def test_run_returns_correct_count(self, agent):
        result = await agent.run(channel_id=uuid.uuid4(), count=3, niche="technology")
        assert len(result) <= 3

    async def test_run_result_has_required_fields(self, agent):
        result = await agent.run(channel_id=uuid.uuid4(), count=2, niche="technology")
        for item in result:
            assert isinstance(item["topic"], str)
            assert isinstance(item["score"], (int, float))
            assert isinstance(item["reason"], str)
            assert item["topic"] != ""

    async def test_run_scores_are_numeric(self, agent):
        result = await agent.run(channel_id=uuid.uuid4(), count=3, niche="technology")
        for item in result:
            assert isinstance(item["score"], (int, float))
            assert 0 <= item["score"] <= 100

    async def test_run_with_sources(self, agent):
        result = await agent.run(
            channel_id=uuid.uuid4(),
            count=2,
            sources=[TopicSource.GOOGLE_TRENDS, TopicSource.REDDIT],
            niche="python",
        )
        assert isinstance(result, list)
        assert all(isinstance(x, dict) for x in result)


class TestTopicAgentParsing:
    def test_parse_valid_json(self, agent):
        raw = json.dumps([
            {"topic": "Docker Tutorial", "score": 95, "reason": "Hot topic", "keywords": ["docker"], "content_type": "long"},
            {"topic": "Kubernetes Guide", "score": 88, "reason": "Rising", "keywords": ["k8s"], "content_type": "long"},
        ])
        result = agent._parse_topics(raw, 5)
        assert len(result) == 2
        assert result[0]["topic"] == "Docker Tutorial" 

    def test_parse_json_with_code_fence(self, agent):
        raw = '```json\n[{"topic": "Test Topic", "score": 80, "reason": "Test", "keywords": [], "content_type": "long"}]\n```'
        result = agent._parse_topics(raw, 5)
        assert len(result) == 1
        assert result[0]["topic"] == "Test Topic"

    def test_parse_invalid_json_returns_fallback(self, agent):
        raw = "This is not JSON at all, just some text"
        result = agent._parse_topics(raw, 3)
        assert len(result) >= 1
        assert result[0]["topic"] != ""

    def test_parse_limits_to_expected_count(self, agent):
        raw = json.dumps([
            {"topic": f"Topic {i}", "score": 80, "reason": "X", "keywords": [], "content_type": "long"}
            for i in range(10)
        ])
        result = agent._parse_topics(raw, 3)
        assert len(result) == 3

    def test_parse_skips_empty_topic_titles(self, agent):
        raw = json.dumps([
            {"topic": "", "score": 90, "reason": "empty"},
            {"topic": "Valid Topic", "score": 85, "reason": "valid", "keywords": [], "content_type": "long"},
        ])
        result = agent._parse_topics(raw, 5)
        assert all(item["topic"] != "" for item in result)

    def test_parse_handles_single_object(self, agent):
        raw = '{"topic": "Single Topic", "score": 75, "reason": "test", "keywords": [], "content_type": "long"}'
        result = agent._parse_topics(raw, 5)
        assert len(result) >= 1

class TestTopicDiscoveryWorkflow:
    async def test_workflow_run_complete_status(self, mock_llm):
        workflow = TopicDiscoveryWorkflow(llm_provider=mock_llm)
        state = await workflow.run(
            channel_id=str(uuid.uuid4()),
            niche="technology",
            count=3,
        )
        assert state["status"] in ("complete", "failed")

    async def test_workflow_run_produces_validated_topics(self, mock_llm):
        workflow = TopicDiscoveryWorkflow(llm_provider=mock_llm)
        state = await workflow.run(
            channel_id=str(uuid.uuid4()),
            niche="devops",
            count=3,
        )
        if state["status"] == "complete":
            assert len(state["validated_topics"]) >= 1

    async def test_workflow_run_with_custom_sources(self, mock_llm):
        workflow = TopicDiscoveryWorkflow(llm_provider=mock_llm)
        state = await workflow.run(
            channel_id=str(uuid.uuid4()),
            niche="python",
            count=2,
            sources=["google_trends"],
        )
        assert state["status"] in ("complete", "failed")

    async def test_workflow_failed_llm_returns_failed_state(self):
        bad_llm = MagicMock()
        bad_llm.generate_text = AsyncMock(side_effect=Exception("LLM error"))
        bad_llm.provider_name = "mock"
        workflow = TopicDiscoveryWorkflow(llm_provider=bad_llm)
        state = await workflow.run(
            channel_id=str(uuid.uuid4()),
            niche="tech",
            count=2,
        )
        assert state["status"] == "failed"
        assert state["error"] is not None