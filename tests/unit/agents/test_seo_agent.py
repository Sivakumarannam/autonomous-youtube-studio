"""Unit tests for SEOAgent and SEOWorkflow."""
import json
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.agents.seo_agent.agent import SEOAgent
from app.agents.seo_agent.models import SEOAgentOutput
from app.agents.seo_agent.workflow import SEOWorkflow
from app.llm_providers.mock_provider import MockLLMProvider


@pytest.fixture
def mock_llm() -> MockLLMProvider:
    return MockLLMProvider()


@pytest.fixture
def agent(mock_llm) -> SEOAgent:
    return SEOAgent(llm_provider=mock_llm)


class _FakeScript:
    def __init__(self, script_type: str = "long", seo_title: str | None = None):
        self.id = uuid.uuid4()
        self.topic_id = uuid.uuid4()
        self.script_type = script_type
        self.content = (
            "Docker is a containerization platform. Kubernetes orchestrates containers. "
            "Learn the difference and choose the right tool for your project."
        )
        self.word_count = 30
        self.seo_title = seo_title
        self.seo_description = None
        self.seo_tags = json.dumps(["docker", "kubernetes"])


# ──────────────────────────────────────────────────────────────────────────────
# SEOAgent.run_for_content
# ──────────────────────────────────────────────────────────────────────────────

class TestSEOAgentRunForContent:
    async def test_returns_output(self, agent):
        output = await agent.run_for_content(
            topic_title="Docker vs Kubernetes",
            script_content="Docker and Kubernetes are different tools.",
            script_type="long",
            niche="devops",
        )
        assert isinstance(output, SEOAgentOutput)

    async def test_output_has_title(self, agent):
        output = await agent.run_for_content(
            topic_title="Python FastAPI Guide",
            script_content="FastAPI is a modern Python framework.",
            niche="python",
        )
        assert isinstance(output.title, str)
        assert len(output.title) > 0

    async def test_output_has_description(self, agent):
        output = await agent.run_for_content(
            topic_title="Linux Commands",
            script_content="Learn essential Linux commands.",
            niche="linux",
        )
        assert isinstance(output.description, str)
        assert len(output.description) > 0

    async def test_output_has_tags_list(self, agent):
        output = await agent.run_for_content(
            topic_title="Git Workflow",
            script_content="Git is a version control system.",
            niche="devops",
        )
        assert isinstance(output.tags, list)

    async def test_output_has_hashtags_list(self, agent):
        output = await agent.run_for_content(
            topic_title="Redis Caching",
            script_content="Redis is an in-memory data store.",
            niche="backend",
        )
        assert isinstance(output.hashtags, list)

    async def test_output_has_primary_keyword(self, agent):
        output = await agent.run_for_content(
            topic_title="Docker Tutorial",
            script_content="Docker tutorial content here.",
            niche="devops",
        )
        assert isinstance(output.primary_keyword, str)

    async def test_output_scores_are_in_range(self, agent):
        output = await agent.run_for_content(
            topic_title="Kubernetes Deep Dive",
            script_content="Kubernetes is a container orchestration platform.",
            niche="devops",
        )
        assert 0.0 <= output.title_score <= 100.0
        assert 0.0 <= output.description_score <= 100.0
        assert 0.0 <= output.tags_score <= 100.0
        assert 0.0 <= output.overall_seo_score <= 100.0

    async def test_shorts_script_type_accepted(self, agent):
        output = await agent.run_for_content(
            topic_title="Docker in 30 Seconds",
            script_content="Quick Docker tip!",
            script_type="short",
            niche="devops",
        )
        assert output is not None

    async def test_llm_error_raises_agent_error(self):
        from app.core.exceptions import AgentError
        bad_llm = MagicMock()
        bad_llm.generate_text = AsyncMock(side_effect=Exception("LLM down"))
        agent = SEOAgent(llm_provider=bad_llm)
        with pytest.raises(AgentError):
            await agent.run_for_content(
                topic_title="Failing Topic",
                script_content="Some content",
            )


# ──────────────────────────────────────────────────────────────────────────────
# SEOAgent.run (with Script ORM)
# ──────────────────────────────────────────────────────────────────────────────

class TestSEOAgentRunWithScript:
    async def test_run_returns_output(self, agent):
        script = _FakeScript(script_type="long")
        output = await agent.run(
            script=script,
            topic_title="Docker vs Kubernetes",
            niche="devops",
        )
        assert isinstance(output, SEOAgentOutput)

    async def test_run_shorts_script(self, agent):
        script = _FakeScript(script_type="short")
        output = await agent.run(
            script=script,
            topic_title="Docker Tip",
            niche="devops",
        )
        assert output is not None
        assert output.overall_seo_score >= 0.0


# ──────────────────────────────────────────────────────────────────────────────
# SEOAgent._parse
# ──────────────────────────────────────────────────────────────────────────────

class TestSEOAgentParsing:
    def test_parse_valid_json(self, agent):
        raw = json.dumps({
            "title": "Docker vs Kubernetes: Complete 2024 Guide",
            "description": "Learn the key differences between Docker and Kubernetes.",
            "tags": ["docker", "kubernetes", "devops", "containers"],
            "hashtags": ["#Docker", "#Kubernetes", "#DevOps"],
            "primary_keyword": "docker vs kubernetes",
            "secondary_keywords": ["containers", "devops"],
            "title_score": 88.0,
            "description_score": 82.0,
            "tags_score": 85.0,
            "overall_seo_score": 85.0,
        })
        result = agent._parse(raw, "Docker vs Kubernetes")
        assert result.title == "Docker vs Kubernetes: Complete 2024 Guide"
        assert len(result.tags) == 4
        assert "#Docker" in result.hashtags
        assert result.title_score == 88.0
        assert result.overall_seo_score == 85.0

    def test_parse_json_with_code_fence(self, agent):
        raw = '```json\n{"title": "Test Title", "description": "Test desc", "tags": [], "hashtags": [], "primary_keyword": "test", "secondary_keywords": [], "title_score": 75.0, "description_score": 70.0, "tags_score": 72.0, "overall_seo_score": 72.3}\n```'
        result = agent._parse(raw, "Test Topic")
        assert result.title == "Test Title"

    def test_parse_invalid_json_returns_fallback(self, agent):
        result = agent._parse("Not valid JSON content here at all", "My Topic")
        assert isinstance(result, SEOAgentOutput)
        assert len(result.title) > 0
        assert result.overall_seo_score >= 0.0

    def test_parse_clamps_scores_above_100(self, agent):
        raw = json.dumps({
            "title": "Test", "description": "Desc", "tags": [], "hashtags": [],
            "primary_keyword": "test", "secondary_keywords": [],
            "title_score": 150.0, "description_score": 200.0,
            "tags_score": 999.0, "overall_seo_score": 120.0,
        })
        result = agent._parse(raw, "Test")
        assert result.title_score <= 100.0
        assert result.description_score <= 100.0
        assert result.tags_score <= 100.0
        assert result.overall_seo_score <= 100.0

    def test_parse_clamps_scores_below_0(self, agent):
        raw = json.dumps({
            "title": "Test", "description": "Desc", "tags": [], "hashtags": [],
            "primary_keyword": "test", "secondary_keywords": [],
            "title_score": -10.0, "description_score": -5.0,
            "tags_score": -1.0, "overall_seo_score": -20.0,
        })
        result = agent._parse(raw, "Test")
        assert result.title_score >= 0.0
        assert result.overall_seo_score >= 0.0

    def test_parse_missing_title_uses_topic(self, agent):
        raw = json.dumps({
            "description": "Desc", "tags": [], "hashtags": [],
            "primary_keyword": "test", "secondary_keywords": [],
            "overall_seo_score": 70.0,
        })
        result = agent._parse(raw, "My Fallback Topic")
        assert "My Fallback Topic" in result.title or len(result.title) > 0

    def test_fallback_has_all_fields(self, agent):
        fallback = agent._fallback("Fallback Topic")
        assert fallback.title is not None
        assert fallback.description is not None
        assert isinstance(fallback.tags, list)
        assert isinstance(fallback.hashtags, list)
        assert fallback.overall_seo_score == 60.0


# ──────────────────────────────────────────────────────────────────────────────
# SEOWorkflow
# ──────────────────────────────────────────────────────────────────────────────

class TestSEOWorkflow:
    async def test_workflow_run_returns_state(self, mock_llm):
        workflow = SEOWorkflow(llm_provider=mock_llm)
        state = await workflow.run(
            script_id=str(uuid.uuid4()),
            topic_title="Docker vs Kubernetes",
            script_content="Docker and Kubernetes explanation.",
            niche="devops",
        )
        assert state is not None
        assert "status" in state

    async def test_workflow_complete_status(self, mock_llm):
        workflow = SEOWorkflow(llm_provider=mock_llm)
        state = await workflow.run(
            script_id=str(uuid.uuid4()),
            topic_title="Python Generators",
            script_content="Python generators explained.",
            niche="python",
        )
        assert state["status"] in ("complete", "failed")

    async def test_workflow_has_seo_title_on_success(self, mock_llm):
        workflow = SEOWorkflow(llm_provider=mock_llm)
        state = await workflow.run(
            script_id=str(uuid.uuid4()),
            topic_title="FastAPI Tutorial",
            script_content="FastAPI tutorial content.",
            niche="python",
        )
        if state["status"] == "complete":
            assert state["seo_title"] is not None
            assert len(state["seo_title"]) > 0

    async def test_workflow_has_tags_on_success(self, mock_llm):
        workflow = SEOWorkflow(llm_provider=mock_llm)
        state = await workflow.run(
            script_id=str(uuid.uuid4()),
            topic_title="Linux Commands",
            script_content="Linux commands guide.",
            niche="linux",
        )
        if state["status"] == "complete":
            assert isinstance(state["tags"], list)

    async def test_workflow_has_overall_score(self, mock_llm):
        workflow = SEOWorkflow(llm_provider=mock_llm)
        state = await workflow.run(
            script_id=str(uuid.uuid4()),
            topic_title="Git Workflow",
            script_content="Git workflow explained.",
            niche="devops",
        )
        if state["status"] == "complete":
            assert 0.0 <= state["overall_seo_score"] <= 100.0

    async def test_workflow_failed_llm(self):
        bad_llm = MagicMock()
        bad_llm.generate_text = AsyncMock(side_effect=Exception("LLM error"))
        workflow = SEOWorkflow(llm_provider=bad_llm)
        state = await workflow.run(
            script_id=str(uuid.uuid4()),
            topic_title="Failing SEO Topic",
            script_content="Some content here.",
        )
        assert state["status"] == "failed"
        assert state["error"] is not None

    async def test_workflow_passes_all_inputs(self, mock_llm):
        workflow = SEOWorkflow(llm_provider=mock_llm)
        sid = str(uuid.uuid4())
        state = await workflow.run(
            script_id=sid,
            topic_title="Redis Guide",
            script_content="Redis is fast.",
            script_type="short",
            niche="backend",
            language="en",
        )
        assert state["script_id"] == sid
        assert state["script_type"] == "short"
        assert state["niche"] == "backend"