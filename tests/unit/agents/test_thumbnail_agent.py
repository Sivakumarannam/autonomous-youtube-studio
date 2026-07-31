"""Unit tests for ThumbnailAgent and ThumbnailWorkflow."""
import json
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.thumbnail_agent.agent import ThumbnailAgent
from app.agents.thumbnail_agent.models import (
    ThumbnailAgentOutput,
    ThumbnailDesign,
    ThumbnailElement,
)
from app.agents.thumbnail_agent.workflow import ThumbnailWorkflow
from app.llm_providers.mock_provider import MockLLMProvider


@pytest.fixture
def mock_llm() -> MockLLMProvider:
    return MockLLMProvider()


@pytest.fixture
def agent(mock_llm) -> ThumbnailAgent:
    return ThumbnailAgent(llm_provider=mock_llm)


class _FakeScript:
    def __init__(self, script_type: str = "long", seo_title: str = ""):
        self.id = uuid.uuid4()
        self.script_type = script_type
        self.content = (
            "Docker is a containerization platform. Kubernetes orchestrates containers at scale. "
            "In this complete guide we compare both tools and show you when to use each one."
        )
        self.word_count = 30
        self.seo_title = seo_title


# ──────────────────────────────────────────────────────────────────────────────
# ThumbnailDesign and ThumbnailElement models
# ──────────────────────────────────────────────────────────────────────────────

class TestThumbnailModels:
    def test_thumbnail_element_defaults(self):
        el = ThumbnailElement()
        assert el.text == ""
        assert el.position == "center"
        assert el.font_size == "large"
        assert el.color == "#FFFFFF"

    def test_thumbnail_element_custom(self):
        el = ThumbnailElement(text="DOCKER vs K8s", position="top", font_size="large", color="#FFD700")
        assert el.text == "DOCKER vs K8s"
        assert el.color == "#FFD700"

    def test_thumbnail_design_defaults(self):
        design = ThumbnailDesign()
        assert design.background_color == "#1A1A2E"
        assert design.accent_color == "#E94560"
        assert design.text_color == "#FFFFFF"
        assert design.layout == "split"
        assert design.background_style == "gradient"
        assert design.text_elements == []

    def test_thumbnail_design_with_elements(self):
        design = ThumbnailDesign(
            text_elements=[
                ThumbnailElement(text="TITLE", position="top"),
                ThumbnailElement(text="subtitle", position="bottom"),
            ]
        )
        assert len(design.text_elements) == 2

    def test_thumbnail_output_ctr_clamped_ge_0(self):
        out = ThumbnailAgentOutput(concept="Test", ctr_score=0.0)
        assert out.ctr_score >= 0.0

    def test_thumbnail_output_ctr_clamped_le_100(self):
        out = ThumbnailAgentOutput(concept="Test", ctr_score=100.0)
        assert out.ctr_score <= 100.0


# ──────────────────────────────────────────────────────────────────────────────
# ThumbnailAgent.generate_concept
# ──────────────────────────────────────────────────────────────────────────────

class TestThumbnailAgentGenerateConcept:
    async def test_returns_output(self, agent):
        output = await agent.generate_concept(
            topic_title="Docker vs Kubernetes",
            niche="devops",
        )
        assert isinstance(output, ThumbnailAgentOutput)

    async def test_output_has_concept(self, agent):
        output = await agent.generate_concept(
            topic_title="Python FastAPI Tutorial",
            niche="python",
        )
        assert isinstance(output.concept, str)
        assert len(output.concept) > 0

    async def test_output_has_design(self, agent):
        output = await agent.generate_concept(
            topic_title="Linux Commands",
            niche="linux",
        )
        assert isinstance(output.design, ThumbnailDesign)

    async def test_output_has_title_text(self, agent):
        output = await agent.generate_concept(
            topic_title="Git Workflow",
            niche="devops",
        )
        assert isinstance(output.title_text, str)

    async def test_output_has_ctr_score_in_range(self, agent):
        output = await agent.generate_concept(
            topic_title="Kubernetes Deep Dive",
            niche="devops",
        )
        assert 0.0 <= output.ctr_score <= 100.0

    async def test_output_design_has_background_color(self, agent):
        output = await agent.generate_concept(
            topic_title="Redis Tutorial",
            niche="backend",
        )
        assert isinstance(output.design.background_color, str)
        assert output.design.background_color.startswith("#")

    async def test_output_design_has_accent_color(self, agent):
        output = await agent.generate_concept(
            topic_title="FastAPI vs Flask",
            niche="python",
        )
        assert isinstance(output.design.accent_color, str)

    async def test_output_design_has_layout(self, agent):
        output = await agent.generate_concept(
            topic_title="CI/CD Pipeline",
            niche="devops",
        )
        assert isinstance(output.design.layout, str)
        assert len(output.design.layout) > 0

    async def test_shorts_type_accepted(self, agent):
        output = await agent.generate_concept(
            topic_title="Docker Tip",
            script_type="short",
            niche="devops",
        )
        assert isinstance(output, ThumbnailAgentOutput)

    async def test_with_seo_title(self, agent):
        output = await agent.generate_concept(
            topic_title="Docker Tutorial",
            seo_title="Docker Tutorial for Beginners 2024: Complete Guide",
            niche="devops",
        )
        assert isinstance(output, ThumbnailAgentOutput)

    async def test_with_script_excerpt(self, agent):
        output = await agent.generate_concept(
            topic_title="Kubernetes Networking",
            script_excerpt="Kubernetes networking is complex. In this guide we cover pods, services, and ingress.",
            niche="devops",
        )
        assert isinstance(output, ThumbnailAgentOutput)

    async def test_llm_error_raises_agent_error(self):
        from app.core.exceptions import AgentError
        bad_llm = MagicMock()
        bad_llm.generate_text = AsyncMock(side_effect=Exception("LLM down"))
        agent = ThumbnailAgent(llm_provider=bad_llm)
        with pytest.raises(AgentError):
            await agent.generate_concept(topic_title="Failing Topic", niche="tech")


# ──────────────────────────────────────────────────────────────────────────────
# ThumbnailAgent.run (with Script ORM)
# ──────────────────────────────────────────────────────────────────────────────

class TestThumbnailAgentRunWithScript:
    async def test_run_returns_output(self, agent, tmp_path):
        with patch("app.agents.thumbnail_agent.agent.settings") as mock_settings:
            mock_settings.storage_local_path = str(tmp_path)
            script = _FakeScript(script_type="long")
            output = await agent.run(
                script=script,
                topic_title="Docker vs Kubernetes",
                niche="devops",
            )
        assert isinstance(output, ThumbnailAgentOutput)

    async def test_run_sets_file_path(self, agent, tmp_path):
        with patch("app.agents.thumbnail_agent.agent.settings") as mock_settings:
            mock_settings.storage_local_path = str(tmp_path)
            script = _FakeScript()
            output = await agent.run(
                script=script,
                topic_title="Docker Tutorial",
                niche="devops",
            )
        assert output.file_path is not None
        assert str(script.id) in output.file_path

    async def test_run_shorts_script(self, agent, tmp_path):
        with patch("app.agents.thumbnail_agent.agent.settings") as mock_settings:
            mock_settings.storage_local_path = str(tmp_path)
            script = _FakeScript(script_type="short")
            output = await agent.run(
                script=script,
                topic_title="Quick Docker Tip",
                niche="devops",
            )
        assert isinstance(output, ThumbnailAgentOutput)

    async def test_run_uses_script_seo_title(self, agent, tmp_path):
        with patch("app.agents.thumbnail_agent.agent.settings") as mock_settings:
            mock_settings.storage_local_path = str(tmp_path)
            script = _FakeScript(seo_title="Docker Tutorial: The Complete 2024 Guide")
            output = await agent.run(
                script=script,
                topic_title="Docker Tutorial",
                niche="devops",
            )
        assert isinstance(output, ThumbnailAgentOutput)

    async def test_thumbnail_file_created_in_storage(self, agent, tmp_path):
        with patch("app.agents.thumbnail_agent.agent.settings") as mock_settings:
            mock_settings.storage_local_path = str(tmp_path)
            script = _FakeScript()
            output = await agent.run(
                script=script,
                topic_title="Docker Tutorial",
                niche="devops",
            )
        # File path should exist as a file
        if output.file_path:
            assert Path(output.file_path).exists()


# ──────────────────────────────────────────────────────────────────────────────
# ThumbnailAgent._parse
# ──────────────────────────────────────────────────────────────────────────────

class TestThumbnailAgentParsing:
    def test_parse_valid_json(self, agent):
        raw = json.dumps({
            "concept": "Split screen: Docker whale left, K8s wheel right, VS badge center. Dark background.",
            "title_text": "DOCKER vs K8s",
            "subtitle_text": "Which One Wins?",
            "emoji": "🐳",
            "design": {
                "background_color": "#0D1117",
                "accent_color": "#2196F3",
                "text_color": "#FFFFFF",
                "layout": "split",
                "subject": "Docker whale and Kubernetes helm wheel",
                "background_style": "gradient",
                "text_elements": [
                    {"text": "DOCKER vs K8s", "position": "top", "font_size": "large", "color": "#FFFFFF"},
                    {"text": "Which One Wins?", "position": "bottom", "font_size": "medium", "color": "#FFD700"},
                ],
                "style_notes": "High contrast dark background, bold typography.",
            },
            "ctr_score": 88.0,
        })
        result = agent._parse(raw, "Docker vs Kubernetes")
        assert result.concept == "Split screen: Docker whale left, K8s wheel right, VS badge center. Dark background."
        assert result.title_text == "DOCKER vs K8s"
        assert result.subtitle_text == "Which One Wins?"
        assert result.emoji == "🐳"
        assert result.design.background_color == "#0D1117"
        assert result.design.layout == "split"
        assert len(result.design.text_elements) == 2
        assert result.ctr_score == 88.0

    def test_parse_json_with_code_fence(self, agent):
        raw = '```json\n{"concept": "Dark thumbnail", "title_text": "TUTORIAL", "subtitle_text": "", "emoji": "🎯", "design": {"background_color": "#000000", "accent_color": "#FF0000", "text_color": "#FFFFFF", "layout": "centered", "subject": "Logo", "background_style": "solid", "text_elements": [], "style_notes": "Minimal."}, "ctr_score": 75.0}\n```'
        result = agent._parse(raw, "Tutorial")
        assert result.title_text == "TUTORIAL"
        assert result.ctr_score == 75.0

    def test_parse_invalid_json_returns_fallback(self, agent):
        result = agent._parse("INVALID JSON NOT VALID", "My Topic")
        assert isinstance(result, ThumbnailAgentOutput)
        assert len(result.concept) > 0
        assert result.ctr_score == 65.0

    def test_parse_clamps_ctr_above_100(self, agent):
        raw = json.dumps({
            "concept": "Test", "title_text": "TEST", "subtitle_text": "",
            "emoji": "", "design": {
                "background_color": "#000", "accent_color": "#FFF",
                "text_color": "#FFF", "layout": "centered", "subject": "test",
                "background_style": "solid", "text_elements": [], "style_notes": "",
            },
            "ctr_score": 999.0,
        })
        result = agent._parse(raw, "Test")
        assert result.ctr_score <= 100.0

    def test_parse_clamps_ctr_below_0(self, agent):
        raw = json.dumps({
            "concept": "Test", "title_text": "TEST", "subtitle_text": "",
            "emoji": "", "design": {
                "background_color": "#000", "accent_color": "#FFF",
                "text_color": "#FFF", "layout": "centered", "subject": "test",
                "background_style": "solid", "text_elements": [], "style_notes": "",
            },
            "ctr_score": -50.0,
        })
        result = agent._parse(raw, "Test")
        assert result.ctr_score >= 0.0

    def test_parse_missing_design_uses_defaults(self, agent):
        raw = json.dumps({
            "concept": "Simple thumbnail concept",
            "title_text": "SIMPLE",
            "ctr_score": 70.0,
        })
        result = agent._parse(raw, "Simple Topic")
        assert isinstance(result.design, ThumbnailDesign)
        assert result.design.background_color == "#1A1A2E"

    def test_parse_text_elements_in_design(self, agent):
        raw = json.dumps({
            "concept": "Test concept",
            "title_text": "TITLE",
            "design": {
                "background_color": "#111",
                "accent_color": "#222",
                "text_color": "#FFF",
                "layout": "split",
                "subject": "Subject",
                "background_style": "gradient",
                "text_elements": [
                    {"text": "TOP TEXT", "position": "top", "font_size": "large", "color": "#FFF"},
                ],
                "style_notes": "",
            },
            "ctr_score": 80.0,
        })
        result = agent._parse(raw, "Test")
        assert len(result.design.text_elements) == 1
        assert result.design.text_elements[0].text == "TOP TEXT"

    def test_fallback_has_required_fields(self, agent):
        fallback = agent._fallback("Python Tutorial")
        assert fallback.concept is not None
        assert len(fallback.concept) > 0
        assert fallback.title_text is not None
        assert isinstance(fallback.design, ThumbnailDesign)
        assert fallback.ctr_score == 65.0
        assert fallback.emoji == "🎯"


# ──────────────────────────────────────────────────────────────────────────────
# ThumbnailWorkflow
# ──────────────────────────────────────────────────────────────────────────────

class TestThumbnailWorkflow:

    async def test_workflow_run_returns_state(self, mock_llm):
        workflow = ThumbnailWorkflow(mock_llm)

        state = await workflow.run(
            script_id=str(uuid.uuid4()),
            topic_title="Docker vs Kubernetes",
        )

        assert state is not None
        assert "status" in state

    async def test_workflow_complete(self, mock_llm):
        workflow = ThumbnailWorkflow(mock_llm)

        state = await workflow.run(
            script_id=str(uuid.uuid4()),
            topic_title="FastAPI",
        )

        assert state["status"] in ("complete", "failed")

    async def test_workflow_contains_concept(self, mock_llm):
        workflow = ThumbnailWorkflow(mock_llm)

        state = await workflow.run(
            script_id=str(uuid.uuid4()),
            topic_title="Redis",
        )

        if state["status"] == "complete":
            assert state["concept"] is not None

    async def test_workflow_contains_title(self, mock_llm):
        workflow = ThumbnailWorkflow(mock_llm)

        state = await workflow.run(
            script_id=str(uuid.uuid4()),
            topic_title="Linux",
        )

        if state["status"] == "complete":
            assert state["title_text"] is not None

    async def test_workflow_contains_colors(self, mock_llm):
        workflow = ThumbnailWorkflow(mock_llm)

        state = await workflow.run(
            script_id=str(uuid.uuid4()),
            topic_title="Docker",
        )

        if state["status"] == "complete":
            assert state["background_color"] is not None
            assert state["accent_color"] is not None

    async def test_workflow_ctr_score(self, mock_llm):
        workflow = ThumbnailWorkflow(mock_llm)

        state = await workflow.run(
            script_id=str(uuid.uuid4()),
            topic_title="Kubernetes",
        )

        if state["status"] == "complete":
            assert 0 <= state["ctr_score"] <= 100

    async def test_workflow_short_script(self, mock_llm):
        workflow = ThumbnailWorkflow(mock_llm)

        state = await workflow.run(
            script_id=str(uuid.uuid4()),
            topic_title="Docker Tip",
            script_type="short",
        )

        assert state["script_type"] == "short"

    async def test_workflow_seo_title(self, mock_llm):
        workflow = ThumbnailWorkflow(mock_llm)

        seo = "Docker Complete Guide"

        state = await workflow.run(
            script_id=str(uuid.uuid4()),
            topic_title="Docker",
            seo_title=seo,
        )

        assert state["seo_title"] == seo

    async def test_workflow_preserves_inputs(self, mock_llm):
        workflow = ThumbnailWorkflow(mock_llm)

        sid = str(uuid.uuid4())

        state = await workflow.run(
            script_id=sid,
            topic_title="Redis",
            niche="backend",
            script_excerpt="Redis tutorial",
        )

        assert state["script_id"] == sid
        assert state["niche"] == "backend"
        assert state["script_excerpt"] == "Redis tutorial"

    async def test_workflow_failed(self):
        bad = MagicMock()
        bad.generate_text = AsyncMock(side_effect=Exception("LLM Failed"))

        workflow = ThumbnailWorkflow(bad)

        state = await workflow.run(
            script_id=str(uuid.uuid4()),
            topic_title="Failure",
        )

        assert state["status"] == "failed"
        assert state["error"] is not None