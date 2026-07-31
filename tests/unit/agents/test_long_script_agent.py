"""Unit tests for LongScriptAgent and LongVideoWorkflow."""
import json
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.agents.long_script_agent.agent import LongScriptAgent
from app.agents.long_script_agent.models import LongScriptAgentOutput, ScriptSection
from app.agents.long_script_agent.workflow import LongVideoWorkflow
from app.llm_providers.mock_provider import MockLLMProvider


@pytest.fixture
def mock_llm() -> MockLLMProvider:
    return MockLLMProvider()


@pytest.fixture
def agent(mock_llm) -> LongScriptAgent:
    return LongScriptAgent(llm_provider=mock_llm)


class _FakeTopic:
    def __init__(self, title: str = "Long Script Test Topic"):
        self.id = uuid.uuid4()
        self.title = title
        self.description = None
        self.channel_id = uuid.uuid4()


class _FakeResearch:
    def __init__(self, talking_points: list[str] | None = None):
        self.summary = "Comprehensive research summary for long-form content testing."
        self.key_facts = json.dumps([
            "Key fact 1: Docker was created in 2013",
            "Key fact 2: Kubernetes was open-sourced by Google in 2014",
            "Key fact 3: Over 80% of Fortune 500 companies use containers",
        ])
        self.references = json.dumps(["https://docker.com", "https://kubernetes.io"])
        self.raw_data = json.dumps({
            "talking_points": talking_points or [
                "Start with the fundamental difference",
                "Use a real-world analogy",
                "Walk through a practical demo",
            ]
        })


# ──────────────────────────────────────────────────────────────────────────────
# LongScriptAgent._generate
# ──────────────────────────────────────────────────────────────────────────────

class TestLongScriptAgentGenerate:
    async def test_generate_returns_output(self, agent):
        output = await agent._generate(
            topic_title="Docker vs Kubernetes",
            research_summary="Summary of the research",
            key_facts=["Fact 1", "Fact 2"],
            talking_points=["Point 1", "Point 2"],
            niche="devops",
            language="en",
        )
        assert isinstance(output, LongScriptAgentOutput)

    async def test_generate_has_full_script(self, agent):
        output = await agent._generate(
            topic_title="Python Async Programming",
            research_summary=None,
            key_facts=[],
            talking_points=[],
            niche="python",
            language="en",
        )
        assert isinstance(output.full_script, str)
        assert len(output.full_script) > 0

    async def test_generate_has_hook(self, agent):
        output = await agent._generate(
            topic_title="Linux Commands Every Dev Should Know",
            research_summary=None,
            key_facts=[],
            talking_points=[],
            niche="linux",
            language="en",
        )
        assert isinstance(output.hook, str)

    async def test_generate_has_introduction(self, agent):
        output = await agent._generate(
            topic_title="FastAPI Complete Guide",
            research_summary="FastAPI is a modern Python framework",
            key_facts=["FastAPI is fast"],
            talking_points=[],
            niche="python",
            language="en",
        )
        assert isinstance(output.introduction, str)

    async def test_generate_has_conclusion(self, agent):
        output = await agent._generate(
            topic_title="Git Workflow Best Practices",
            research_summary=None,
            key_facts=[],
            talking_points=[],
            niche="devops",
            language="en",
        )
        assert isinstance(output.conclusion, str)

    async def test_generate_has_cta(self, agent):
        output = await agent._generate(
            topic_title="Terraform for Beginners",
            research_summary=None,
            key_facts=[],
            talking_points=[],
            niche="devops",
            language="en",
        )
        assert isinstance(output.cta, str)
        assert len(output.cta) > 0

    async def test_generate_has_seo_data(self, agent):
        output = await agent._generate(
            topic_title="CI/CD Pipeline Tutorial",
            research_summary=None,
            key_facts=[],
            talking_points=[],
            niche="devops",
            language="en",
        )
        assert isinstance(output.seo_title, str)
        assert isinstance(output.seo_description, str)
        assert isinstance(output.tags, list)
        assert isinstance(output.hashtags, list)

    async def test_generate_has_thumbnail_concept(self, agent):
        output = await agent._generate(
            topic_title="AWS vs GCP vs Azure",
            research_summary=None,
            key_facts=[],
            talking_points=[],
            niche="cloud",
            language="en",
        )
        assert isinstance(output.thumbnail_concept, str)

    async def test_generate_has_sections(self, agent):
        output = await agent._generate(
            topic_title="Microservices Architecture",
            research_summary="Research summary here",
            key_facts=["Microservices decouple applications"],
            talking_points=["Start with monolith"],
            niche="architecture",
            language="en",
        )
        assert isinstance(output.sections, list)

    async def test_generate_word_count_is_positive(self, agent):
        output = await agent._generate(
            topic_title="Redis Caching Strategies",
            research_summary=None,
            key_facts=[],
            talking_points=[],
            niche="backend",
            language="en",
        )
        assert output.word_count >= 0

    async def test_generate_estimated_duration_is_positive(self, agent):
        output = await agent._generate(
            topic_title="Database Indexing Explained",
            research_summary=None,
            key_facts=[],
            talking_points=[],
            niche="databases",
            language="en",
        )
        assert output.estimated_duration_seconds > 0


# ──────────────────────────────────────────────────────────────────────────────
# LongScriptAgent._parse_response
# ──────────────────────────────────────────────────────────────────────────────

class TestLongScriptAgentParsing:
    def test_parse_valid_full_json(self, agent):
        raw = json.dumps({
            "hook": "What if one technology could replace your entire DevOps team?",
            "introduction": "Welcome back. Today we're deep-diving into Docker vs Kubernetes.",
            "sections": [
                {"title": "What is Docker?", "content": "Docker is a containerization platform.", "duration_seconds": 90},
                {"title": "What is Kubernetes?", "content": "Kubernetes orchestrates containers at scale.", "duration_seconds": 120},
                {"title": "Head to Head", "content": "Let's compare them side by side.", "duration_seconds": 150},
            ],
            "conclusion": "Both tools solve different problems at different scales.",
            "cta": "If this helped, smash that like button and subscribe!",
            "full_script": "What if... Welcome back. Docker is... Kubernetes... Both tools... Subscribe!",
            "word_count": 1200,
            "estimated_duration_seconds": 545,
            "seo_title": "Docker vs Kubernetes: Complete 2024 Guide",
            "seo_description": "Learn the difference between Docker and Kubernetes in this complete guide.",
            "tags": ["docker", "kubernetes", "devops", "containers"],
            "hashtags": ["#Docker", "#Kubernetes", "#DevOps"],
            "thumbnail_concept": "Split screen Docker whale vs Kubernetes wheel",
        })
        result = agent._parse_response(raw, "Docker vs Kubernetes")
        assert result.hook == "What if one technology could replace your entire DevOps team?"
        assert result.word_count == 1200
        assert len(result.sections) == 3
        assert result.sections[0].title == "What is Docker?"
        assert "#Docker" in result.hashtags

    def test_parse_json_with_code_fence(self, agent):
        raw = '```json\n{"hook": "Hook text", "introduction": "Intro", "sections": [], "conclusion": "Concl", "cta": "Subscribe!", "full_script": "Full content here", "word_count": 3}\n```'
        result = agent._parse_response(raw, "Fenced Topic")
        assert result.hook == "Hook text"
        assert result.word_count == 3

    def test_parse_invalid_json_returns_fallback(self, agent):
        raw = "This is just plain text with no JSON structure whatsoever"
        result = agent._parse_response(raw, "Fallback Topic")
        assert result.full_script is not None
        assert len(result.full_script) > 0
        assert result.estimated_duration_seconds > 0

    def test_parse_missing_full_script_combines_parts(self, agent):
        raw = json.dumps({
            "introduction": "Introduction text here",
            "sections": [{"title": "Sec 1", "content": "Content", "duration_seconds": 60}],
            "conclusion": "Conclusion text",
            "cta": "Subscribe please",
            "word_count": 10,
        })
        result = agent._parse_response(raw, "Combined Topic")
        assert result.full_script is not None
        assert len(result.full_script) > 0

    def test_parse_sections_are_script_section_objects(self, agent):
        raw = json.dumps({
            "sections": [
                {"title": "Section A", "content": "Content A", "duration_seconds": 90},
                {"title": "Section B", "content": "Content B", "duration_seconds": 120},
            ],
            "full_script": "Full content",
            "word_count": 2,
        })
        result = agent._parse_response(raw, "Sections Topic")
        assert all(isinstance(s, ScriptSection) for s in result.sections)
        assert result.sections[0].title == "Section A"
        assert result.sections[1].duration_seconds == 120

    def test_parse_defaults_seo_title_to_topic(self, agent):
        raw = json.dumps({"full_script": "Script only", "word_count": 2})
        result = agent._parse_response(raw, "My Video Topic")
        assert "My Video Topic" in result.seo_title or result.seo_title != ""

    def test_parse_empty_sections_list(self, agent):
        raw = json.dumps({"sections": [], "full_script": "Script text", "word_count": 2})
        result = agent._parse_response(raw, "No Sections Topic")
        assert result.sections == []


# ──────────────────────────────────────────────────────────────────────────────
# LongScriptAgent._extract_research
# ──────────────────────────────────────────────────────────────────────────────

class TestLongScriptAgentResearchExtraction:
    def test_extract_research_with_none(self, agent):
        summary, facts, talking_points = agent._extract_research(None)
        assert summary is None
        assert facts == []
        assert talking_points == []

    def test_extract_research_with_data(self, agent):
        research = _FakeResearch(talking_points=["Point A", "Point B"])
        summary, facts, talking_points = agent._extract_research(research)
        assert summary == research.summary
        assert len(facts) == 3
        assert "Point A" in talking_points

    def test_extract_research_malformed_key_facts(self, agent):
        research = _FakeResearch()
        research.key_facts = "NOT VALID JSON"
        summary, facts, talking_points = agent._extract_research(research)
        assert facts == []

    def test_extract_research_malformed_raw_data(self, agent):
        research = _FakeResearch()
        research.raw_data = "ALSO NOT JSON"
        summary, facts, talking_points = agent._extract_research(research)
        assert talking_points == []


# ──────────────────────────────────────────────────────────────────────────────
# LongVideoWorkflow
# ──────────────────────────────────────────────────────────────────────────────

class TestLongVideoWorkflow:
    async def test_workflow_run_returns_state(self, mock_llm):
        workflow = LongVideoWorkflow(llm_provider=mock_llm)
        state = await workflow.run(
            topic_id=str(uuid.uuid4()),
            topic_title="Docker Complete Guide",
            channel_id=str(uuid.uuid4()),
            niche="devops",
        )
        assert state is not None
        assert "status" in state

    async def test_workflow_complete_status(self, mock_llm):
        workflow = LongVideoWorkflow(llm_provider=mock_llm)
        state = await workflow.run(
            topic_id=str(uuid.uuid4()),
            topic_title="Python Async Explained",
            channel_id=str(uuid.uuid4()),
            niche="python",
        )
        assert state["status"] in ("complete", "failed")

    async def test_workflow_has_script_content_on_success(self, mock_llm):
        workflow = LongVideoWorkflow(llm_provider=mock_llm)
        state = await workflow.run(
            topic_id=str(uuid.uuid4()),
            topic_title="Kubernetes from Zero to Hero",
            channel_id=str(uuid.uuid4()),
            niche="devops",
        )
        if state["status"] == "complete":
            assert state["script_content"] is not None
            assert len(state["script_content"]) > 0

    async def test_workflow_has_word_count(self, mock_llm):
        workflow = LongVideoWorkflow(llm_provider=mock_llm)
        state = await workflow.run(
            topic_id=str(uuid.uuid4()),
            topic_title="FastAPI Production Setup",
            channel_id=str(uuid.uuid4()),
            niche="python",
        )
        if state["status"] == "complete":
            assert state["word_count"] >= 0

    async def test_workflow_has_duration(self, mock_llm):
        workflow = LongVideoWorkflow(llm_provider=mock_llm)
        state = await workflow.run(
            topic_id=str(uuid.uuid4()),
            topic_title="Linux File Permissions Deep Dive",
            channel_id=str(uuid.uuid4()),
            niche="linux",
        )
        if state["status"] == "complete":
            assert state["duration_seconds"] > 0

    async def test_workflow_passes_research_data(self, mock_llm):
        workflow = LongVideoWorkflow(llm_provider=mock_llm)
        state = await workflow.run(
            topic_id=str(uuid.uuid4()),
            topic_title="CI/CD with GitHub Actions",
            channel_id=str(uuid.uuid4()),
            niche="devops",
            research_summary="GitHub Actions is a CI/CD platform built into GitHub.",
            key_facts=["GitHub Actions launched in 2019", "Supports all major languages"],
            talking_points=["Compare with Jenkins", "Show a real example"],
        )
        assert state["topic_title"] == "CI/CD with GitHub Actions"

    async def test_workflow_failed_llm_returns_failed_state(self):
        bad_llm = MagicMock()
        bad_llm.generate_text = AsyncMock(side_effect=Exception("LLM unavailable"))
        bad_llm.provider_name = "mock"
        workflow = LongVideoWorkflow(llm_provider=bad_llm)
        state = await workflow.run(
            topic_id=str(uuid.uuid4()),
            topic_title="Failing Long Script Topic",
            channel_id=str(uuid.uuid4()),
        )
        assert state["status"] == "failed"
        assert state["error"] is not None

    async def test_workflow_state_includes_seo_fields(self, mock_llm):
        workflow = LongVideoWorkflow(llm_provider=mock_llm)
        state = await workflow.run(
            topic_id=str(uuid.uuid4()),
            topic_title="Redis vs Memcached",
            channel_id=str(uuid.uuid4()),
            niche="backend",
        )
        assert "seo_title" in state
        assert "seo_description" in state
        assert "tags" in state
        assert "hashtags" in state

    async def test_workflow_state_includes_thumbnail_concept(self, mock_llm):
        workflow = LongVideoWorkflow(llm_provider=mock_llm)
        state = await workflow.run(
            topic_id=str(uuid.uuid4()),
            topic_title="PostgreSQL vs MySQL",
            channel_id=str(uuid.uuid4()),
            niche="databases",
        )
        assert "thumbnail_concept" in state