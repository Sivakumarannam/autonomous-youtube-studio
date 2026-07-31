"""Unit tests for QualityAgent and QualityWorkflow."""
import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.quality_agent.agent import QualityAgent
from app.agents.quality_agent.models import QualityAgentOutput, QualityScores
from app.agents.quality_agent.workflow import QualityWorkflow
from app.llm_providers.mock_provider import MockLLMProvider


@pytest.fixture
def mock_llm() -> MockLLMProvider:
    return MockLLMProvider()


@pytest.fixture
def agent(mock_llm) -> QualityAgent:
    return QualityAgent(llm_provider=mock_llm)


GOOD_SCRIPT = (
    "Docker is a containerization platform that lets you package applications "
    "with all their dependencies. Created in 2013, it has revolutionised software "
    "delivery. In this video we cover installation, images, containers, and best "
    "practices for production deployments. Follow for more DevOps tutorials!"
)

SHORT_SCRIPT = "Docker packs your app into a container. Runs anywhere. Follow for more tips!"


class _FakeScript:
    def __init__(self, script_type: str = "long", content: str = GOOD_SCRIPT):
        self.id = uuid.uuid4()
        self.topic_id = uuid.uuid4()
        self.script_type = script_type
        self.content = content
        self.word_count = len(content.split())


# ──────────────────────────────────────────────────────────────────────────────
# QualityScores helper model
# ──────────────────────────────────────────────────────────────────────────────

class TestQualityScores:
    def test_overall_is_average_of_seven(self):
        scores = QualityScores(
            grammar_score=90.0,
            fact_consistency_score=80.0,
            engagement_score=85.0,
            retention_score=75.0,
            seo_score=88.0,
            uniqueness_score=70.0,
            readability_score=92.0,
        )
        expected = round((90 + 80 + 85 + 75 + 88 + 70 + 92) / 7, 1)
        assert scores.overall() == expected

    def test_overall_all_zeros(self):
        scores = QualityScores()
        assert scores.overall() == 0.0

    def test_overall_all_hundred(self):
        scores = QualityScores(
            grammar_score=100.0,
            fact_consistency_score=100.0,
            engagement_score=100.0,
            retention_score=100.0,
            seo_score=100.0,
            uniqueness_score=100.0,
            readability_score=100.0,
        )
        assert scores.overall() == 100.0


# ──────────────────────────────────────────────────────────────────────────────
# QualityAgent.evaluate_content
# ──────────────────────────────────────────────────────────────────────────────

class TestQualityAgentEvaluateContent:
    async def test_returns_output(self, agent):
        output = await agent.evaluate_content(
            script_content=GOOD_SCRIPT,
            topic_title="Docker Guide",
            niche="devops",
        )
        assert isinstance(output, QualityAgentOutput)

    async def test_output_has_scores_object(self, agent):
        output = await agent.evaluate_content(script_content=GOOD_SCRIPT, niche="devops")
        assert isinstance(output.scores, QualityScores)

    async def test_grammar_score_in_range(self, agent):
        output = await agent.evaluate_content(script_content=GOOD_SCRIPT, niche="devops")
        assert 0.0 <= output.scores.grammar_score <= 100.0

    async def test_all_scores_in_range(self, agent):
        output = await agent.evaluate_content(script_content=GOOD_SCRIPT, niche="devops")
        for score in [
            output.scores.grammar_score,
            output.scores.fact_consistency_score,
            output.scores.engagement_score,
            output.scores.retention_score,
            output.scores.seo_score,
            output.scores.uniqueness_score,
            output.scores.readability_score,
        ]:
            assert 0.0 <= score <= 100.0

    async def test_overall_score_in_range(self, agent):
        output = await agent.evaluate_content(script_content=GOOD_SCRIPT, niche="devops")
        assert 0.0 <= output.overall_score <= 100.0

    async def test_passed_is_bool(self, agent):
        output = await agent.evaluate_content(script_content=GOOD_SCRIPT, niche="devops")
        assert isinstance(output.passed, bool)

    async def test_feedback_is_string(self, agent):
        output = await agent.evaluate_content(script_content=GOOD_SCRIPT, niche="devops")
        assert isinstance(output.feedback, str)

    async def test_improvement_suggestions_is_list(self, agent):
        output = await agent.evaluate_content(script_content=GOOD_SCRIPT, niche="devops")
        assert isinstance(output.improvement_suggestions, list)

    async def test_short_script_type(self, agent):
        output = await agent.evaluate_content(
            script_content=SHORT_SCRIPT,
            script_type="short",
            topic_title="Docker Tip",
            word_count=15,
        )
        assert isinstance(output, QualityAgentOutput)

    async def test_rejection_reason_set_on_failure(self, agent):
        """When mock returns a failing score, rejection_reason should be populated."""
        failing_response = json.dumps({
            "grammar_score": 30.0,
            "fact_consistency_score": 25.0,
            "engagement_score": 20.0,
            "retention_score": 15.0,
            "seo_score": 35.0,
            "uniqueness_score": 20.0,
            "readability_score": 30.0,
            "overall_score": 25.0,
            "passed": False,
            "feedback": "Script has major issues.",
            "improvement_suggestions": ["Rewrite completely"],
            "rejection_reason": "Score below threshold",
        })
        bad_llm = MagicMock()
        bad_llm.generate_text = AsyncMock(return_value=failing_response)
        failing_agent = QualityAgent(llm_provider=bad_llm)
        output = await failing_agent.evaluate_content(script_content="bad content", niche="tech")
        assert output.passed is False
        assert output.rejection_reason is not None

    async def test_llm_error_raises_agent_error(self):
        from app.core.exceptions import AgentError
        bad_llm = MagicMock()
        bad_llm.generate_text = AsyncMock(side_effect=Exception("LLM crashed"))
        agent = QualityAgent(llm_provider=bad_llm)
        with pytest.raises(AgentError):
            await agent.evaluate_content(script_content="content", niche="tech")


# ──────────────────────────────────────────────────────────────────────────────
# QualityAgent.run (with Script ORM)
# ──────────────────────────────────────────────────────────────────────────────

class TestQualityAgentRunWithScript:
    async def test_run_returns_output(self, agent):
        script = _FakeScript()
        output = await agent.run(script=script, topic_title="Docker Guide", niche="devops")
        assert isinstance(output, QualityAgentOutput)

    async def test_run_short_script(self, agent):
        script = _FakeScript(script_type="short", content=SHORT_SCRIPT)
        output = await agent.run(script=script, topic_title="Docker Tip", niche="devops")
        assert output is not None


# ──────────────────────────────────────────────────────────────────────────────
# QualityAgent._parse
# ──────────────────────────────────────────────────────────────────────────────

class TestQualityAgentParsing:
    def test_parse_valid_json_passing(self, agent):
        raw = json.dumps({
            "grammar_score": 92.0,
            "fact_consistency_score": 88.0,
            "engagement_score": 85.0,
            "retention_score": 80.0,
            "seo_score": 90.0,
            "uniqueness_score": 78.0,
            "readability_score": 88.0,
            "overall_score": 86.0,
            "passed": True,
            "feedback": "Excellent script with strong hook and clear CTA.",
            "improvement_suggestions": ["Add a statistic in the intro"],
            "rejection_reason": None,
        })
        result = agent._parse(raw)
        assert result.passed is True
        assert result.overall_score == 86.0
        assert result.scores.grammar_score == 92.0
        assert result.rejection_reason is None

    def test_parse_valid_json_failing(self, agent):
        raw = json.dumps({
            "grammar_score": 40.0,
            "fact_consistency_score": 35.0,
            "engagement_score": 30.0,
            "retention_score": 25.0,
            "seo_score": 45.0,
            "uniqueness_score": 30.0,
            "readability_score": 35.0,
            "overall_score": 34.3,
            "passed": False,
            "feedback": "Script needs significant rework.",
            "improvement_suggestions": ["Rewrite the hook", "Add examples"],
            "rejection_reason": "Overall score 34.3 is below threshold 70",
        })
        result = agent._parse(raw)
        assert result.passed is False
        assert result.rejection_reason is not None

    def test_parse_json_with_code_fence(self, agent):
        raw = '```json\n{"grammar_score": 85.0, "fact_consistency_score": 80.0, "engagement_score": 82.0, "retention_score": 78.0, "seo_score": 83.0, "uniqueness_score": 75.0, "readability_score": 86.0, "overall_score": 81.3, "passed": true, "feedback": "Good.", "improvement_suggestions": [], "rejection_reason": null}\n```'
        result = agent._parse(raw)
        assert result.scores.grammar_score == 85.0

    def test_parse_invalid_json_returns_fallback(self, agent):
        result = agent._parse("NOT JSON")
        assert isinstance(result, QualityAgentOutput)
        assert isinstance(result.scores, QualityScores)

    def test_parse_clamps_scores(self, agent):
        raw = json.dumps({
            "grammar_score": 150.0, "fact_consistency_score": -10.0,
            "engagement_score": 80.0, "retention_score": 75.0,
            "seo_score": 200.0, "uniqueness_score": -5.0,
            "readability_score": 85.0, "overall_score": 80.0,
            "passed": True, "feedback": "OK", "improvement_suggestions": [],
        })
        result = agent._parse(raw)
        assert result.scores.grammar_score <= 100.0
        assert result.scores.fact_consistency_score >= 0.0
        assert result.scores.seo_score <= 100.0
        assert result.scores.uniqueness_score >= 0.0

    def test_parse_auto_sets_rejection_reason_when_failed_no_reason(self, agent):
        raw = json.dumps({
            "grammar_score": 30.0, "fact_consistency_score": 30.0,
            "engagement_score": 30.0, "retention_score": 30.0,
            "seo_score": 30.0, "uniqueness_score": 30.0,
            "readability_score": 30.0, "overall_score": 30.0,
            "passed": False, "feedback": "Bad.", "improvement_suggestions": [],
            "rejection_reason": None,
        })
        result = agent._parse(raw)
        assert result.passed is False
        assert result.rejection_reason is not None

    def test_fallback_has_correct_structure(self, agent):
        fallback = agent._fallback()
        assert isinstance(fallback.scores, QualityScores)
        assert fallback.overall_score == 70.0
        assert isinstance(fallback.improvement_suggestions, list)


# ──────────────────────────────────────────────────────────────────────────────
# QualityWorkflow
# ──────────────────────────────────────────────────────────────────────────────

class TestQualityWorkflow:
    async def test_workflow_run_returns_state(self, mock_llm):
        workflow = QualityWorkflow(llm_provider=mock_llm)
        state = await workflow.run(
            script_id=str(uuid.uuid4()),
            script_content=GOOD_SCRIPT,
            topic_title="Docker Guide",
            niche="devops",
        )
        assert state is not None
        assert "status" in state

    async def test_workflow_complete_status(self, mock_llm):
        workflow = QualityWorkflow(llm_provider=mock_llm)
        state = await workflow.run(
            script_id=str(uuid.uuid4()),
            script_content=GOOD_SCRIPT,
            niche="devops",
        )
        assert state["status"] in ("complete", "failed")

    async def test_workflow_has_all_score_fields(self, mock_llm):
        workflow = QualityWorkflow(llm_provider=mock_llm)
        state = await workflow.run(
            script_id=str(uuid.uuid4()),
            script_content=GOOD_SCRIPT,
            niche="devops",
        )
        if state["status"] == "complete":
            for key in [
                "grammar_score", "fact_consistency_score", "engagement_score",
                "retention_score", "seo_score", "uniqueness_score", "readability_score",
                "overall_score",
            ]:
                assert key in state
                assert 0.0 <= state[key] <= 100.0

    async def test_workflow_has_passed_field(self, mock_llm):
        workflow = QualityWorkflow(llm_provider=mock_llm)
        state = await workflow.run(
            script_id=str(uuid.uuid4()),
            script_content=GOOD_SCRIPT,
        )
        assert "passed" in state
        assert isinstance(state["passed"], bool)

    async def test_workflow_failed_llm(self):
        bad_llm = MagicMock()
        bad_llm.generate_text = AsyncMock(side_effect=Exception("LLM down"))
        workflow = QualityWorkflow(llm_provider=bad_llm)
        state = await workflow.run(
            script_id=str(uuid.uuid4()),
            script_content="Some content",
        )
        assert state["status"] == "failed"
        assert state["error"] is not None

    async def test_workflow_short_script_type(self, mock_llm):
        workflow = QualityWorkflow(llm_provider=mock_llm)
        state = await workflow.run(
            script_id=str(uuid.uuid4()),
            script_content=SHORT_SCRIPT,
            script_type="short",
            topic_title="Docker Tip",
            word_count=15,
        )
        assert state["status"] in ("complete", "failed")

    async def test_workflow_has_feedback(self, mock_llm):
        workflow = QualityWorkflow(llm_provider=mock_llm)
        state = await workflow.run(
            script_id=str(uuid.uuid4()),
            script_content=GOOD_SCRIPT,
        )
        if state["status"] == "complete":
            assert isinstance(state["feedback"], str)

    async def test_workflow_has_improvement_suggestions(self, mock_llm):
        workflow = QualityWorkflow(llm_provider=mock_llm)
        state = await workflow.run(
            script_id=str(uuid.uuid4()),
            script_content=GOOD_SCRIPT,
        )
        if state["status"] == "complete":
            assert isinstance(state["improvement_suggestions"], list)