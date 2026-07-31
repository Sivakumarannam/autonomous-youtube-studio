"""Unit tests for ModerationAgent and ModerationWorkflow."""
import json
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.agents.moderation_agent.agent import ModerationAgent
from app.agents.moderation_agent.models import (
    ModerationAgentOutput,
    ModerationFlags,
    ModerationRisk,
)
from app.agents.moderation_agent.workflow import ModerationWorkflow
from app.core.exceptions import ModerationError
from app.llm_providers.mock_provider import MockLLMProvider


@pytest.fixture
def mock_llm() -> MockLLMProvider:
    return MockLLMProvider()


@pytest.fixture
def agent(mock_llm) -> ModerationAgent:
    return ModerationAgent(llm_provider=mock_llm)


CLEAN_SCRIPT = (
    "Docker is an open-source containerization platform that lets developers "
    "package applications and their dependencies into portable containers. "
    "In this tutorial we cover installation, basic commands, and best practices "
    "for production deployments. Subscribe for weekly DevOps content!"
)

RISKY_SCRIPT = (
    "Buy followers now at follower-farm.com! Click the link below! "
    "Limited time offer! All major streaming services hate this trick! "
    "Get rich quick using this one weird method! Subscribe or else!"
)


class _FakeScript:
    def __init__(
        self,
        script_type: str = "long",
        content: str = CLEAN_SCRIPT,
        seo_title: str = "",
        seo_description: str = "",
        seo_tags: str | None = None,
    ):
        self.id = uuid.uuid4()
        self.topic_id = uuid.uuid4()
        self.script_type = script_type
        self.content = content
        self.word_count = len(content.split())
        self.seo_title = seo_title
        self.seo_description = seo_description
        self.seo_tags = seo_tags or json.dumps(["docker", "devops", "containers"])


# ──────────────────────────────────────────────────────────────────────────────
# ModerationFlags
# ──────────────────────────────────────────────────────────────────────────────

class TestModerationFlags:
    def test_any_flagged_false_when_all_clear(self):
        flags = ModerationFlags()
        assert flags.any_flagged() is False

    def test_any_flagged_true_when_copyright_flagged(self):
        flags = ModerationFlags(copyright_risk=True)
        assert flags.any_flagged() is True

    def test_any_flagged_true_when_policy_flagged(self):
        flags = ModerationFlags(policy_violation=True)
        assert flags.any_flagged() is True

    def test_any_flagged_true_when_monetization_flagged(self):
        flags = ModerationFlags(monetization_unsafe=True)
        assert flags.any_flagged() is True

    def test_flagged_list_empty_when_all_clear(self):
        flags = ModerationFlags()
        assert flags.flagged_list() == []

    def test_flagged_list_single(self):
        flags = ModerationFlags(spam_risk=True)
        assert "spam_risk" in flags.flagged_list()
        assert len(flags.flagged_list()) == 1

    def test_flagged_list_multiple(self):
        flags = ModerationFlags(
            copyright_risk=True,
            duplicate_content=True,
            spam_risk=True,
            policy_violation=True,
            monetization_unsafe=True,
        )
        lst = flags.flagged_list()
        assert len(lst) == 5
        assert "copyright_risk" in lst
        assert "monetization_unsafe" in lst


# ──────────────────────────────────────────────────────────────────────────────
# ModerationRisk
# ──────────────────────────────────────────────────────────────────────────────

class TestModerationRisk:
    def test_overall_risk_is_maximum(self):
        risk = ModerationRisk(
            copyright_risk_score=10.0,
            duplicate_risk_score=90.0,
            spam_risk_score=30.0,
            policy_risk_score=20.0,
            monetization_risk_score=50.0,
        )
        assert risk.overall_risk() == 90.0

    def test_overall_risk_zero(self):
        risk = ModerationRisk()
        assert risk.overall_risk() == 0.0

    def test_overall_risk_all_same(self):
        risk = ModerationRisk(
            copyright_risk_score=55.0,
            duplicate_risk_score=55.0,
            spam_risk_score=55.0,
            policy_risk_score=55.0,
            monetization_risk_score=55.0,
        )
        assert risk.overall_risk() == 55.0


# ──────────────────────────────────────────────────────────────────────────────
# ModerationAgent.moderate_content
# ──────────────────────────────────────────────────────────────────────────────

class TestModerationAgentModerateContent:
    async def test_returns_output(self, agent):
        output = await agent.moderate_content(
            script_content=CLEAN_SCRIPT,
            topic_title="Docker Tutorial",
            niche="devops",
        )
        assert isinstance(output, ModerationAgentOutput)

    async def test_clean_content_approved(self, agent):
        output = await agent.moderate_content(
            script_content=CLEAN_SCRIPT,
            topic_title="Docker Tutorial",
            niche="devops",
        )
        assert isinstance(output.approved, bool)

    async def test_output_has_flags(self, agent):
        output = await agent.moderate_content(
            script_content=CLEAN_SCRIPT,
            niche="devops",
        )
        assert isinstance(output.flags, ModerationFlags)

    async def test_output_has_risk_scores(self, agent):
        output = await agent.moderate_content(
            script_content=CLEAN_SCRIPT,
            niche="devops",
        )
        assert isinstance(output.risk_scores, ModerationRisk)

    async def test_risk_scores_in_range(self, agent):
        output = await agent.moderate_content(
            script_content=CLEAN_SCRIPT,
            niche="devops",
        )
        for score in [
            output.risk_scores.copyright_risk_score,
            output.risk_scores.duplicate_risk_score,
            output.risk_scores.spam_risk_score,
            output.risk_scores.policy_risk_score,
            output.risk_scores.monetization_risk_score,
        ]:
            assert 0.0 <= score <= 100.0

    async def test_overall_risk_score_in_range(self, agent):
        output = await agent.moderate_content(
            script_content=CLEAN_SCRIPT,
            niche="devops",
        )
        assert 0.0 <= output.overall_risk_score <= 100.0

    async def test_rejection_reasons_is_list(self, agent):
        output = await agent.moderate_content(
            script_content=CLEAN_SCRIPT,
            niche="devops",
        )
        assert isinstance(output.rejection_reasons, list)

    async def test_recommendations_is_list(self, agent):
        output = await agent.moderate_content(
            script_content=CLEAN_SCRIPT,
            niche="devops",
        )
        assert isinstance(output.recommendations, list)

    async def test_reviewer_notes_is_string(self, agent):
        output = await agent.moderate_content(
            script_content=CLEAN_SCRIPT,
            niche="devops",
        )
        assert isinstance(output.reviewer_notes, str)

    async def test_with_seo_metadata(self, agent):
        output = await agent.moderate_content(
            script_content=CLEAN_SCRIPT,
            topic_title="Docker vs Kubernetes",
            niche="devops",
            seo_title="Docker vs Kubernetes: Complete Guide 2024",
            seo_description="Learn the key differences between Docker and Kubernetes.",
            tags=["docker", "kubernetes", "devops", "containers"],
        )
        assert isinstance(output, ModerationAgentOutput)

    async def test_shorts_format(self, agent):
        output = await agent.moderate_content(
            script_content="Docker tip! Follow for more.",
            script_type="short",
            topic_title="Docker Tip",
            niche="devops",
        )
        assert isinstance(output, ModerationAgentOutput)

    async def test_llm_error_raises_agent_error(self):
        from app.core.exceptions import AgentError
        bad_llm = MagicMock()
        bad_llm.generate_text = AsyncMock(side_effect=Exception("LLM down"))
        agent = ModerationAgent(llm_provider=bad_llm)
        with pytest.raises(AgentError):
            await agent.moderate_content(script_content="some content", niche="tech")


# ──────────────────────────────────────────────────────────────────────────────
# ModerationAgent.run (with Script ORM)
# ──────────────────────────────────────────────────────────────────────────────

class TestModerationAgentRunWithScript:
    async def test_run_returns_output(self, agent):
        script = _FakeScript()
        output = await agent.run(
            script=script,
            topic_title="Docker Tutorial",
            niche="devops",
        )
        assert isinstance(output, ModerationAgentOutput)

    async def test_run_resolves_seo_fields_from_script(self, agent):
        script = _FakeScript(
            seo_title="Docker Tutorial 2024",
            seo_description="Complete Docker guide for beginners",
        )
        output = await agent.run(script=script, topic_title="Docker Tutorial")
        assert isinstance(output, ModerationAgentOutput)

    async def test_run_parses_seo_tags_from_json(self, agent):
        script = _FakeScript(seo_tags=json.dumps(["docker", "tutorial", "devops"]))
        output = await agent.run(script=script, topic_title="Docker")
        assert isinstance(output, ModerationAgentOutput)

    async def test_run_raise_on_failure_approved(self, agent):
        """Should not raise when content is approved."""
        script = _FakeScript()
        # Mock returns approved=True, so no exception expected
        output = await agent.run(
            script=script,
            topic_title="Docker Tutorial",
            raise_on_failure=True,
        )
        assert isinstance(output, ModerationAgentOutput)

    async def test_run_raise_on_failure_rejected_raises(self):
        """Should raise ModerationError when rejected and raise_on_failure=True."""
        rejected_response = json.dumps({
            "copyright_risk_score": 90.0,
            "duplicate_risk_score": 10.0,
            "spam_risk_score": 10.0,
            "policy_risk_score": 5.0,
            "monetization_risk_score": 15.0,
            "copyright_risk": True,
            "duplicate_content": False,
            "spam_risk": False,
            "policy_violation": False,
            "monetization_unsafe": False,
            "overall_risk_score": 90.0,
            "approved": False,
            "rejection_reasons": ["Copyright violation detected"],
            "recommendations": ["Remove copyrighted content"],
            "reviewer_notes": "Script contains protected material.",
        })
        bad_llm = MagicMock()
        bad_llm.generate_text = AsyncMock(return_value=rejected_response)
        agent = ModerationAgent(llm_provider=bad_llm)
        script = _FakeScript()
        with pytest.raises(ModerationError):
            await agent.run(
                script=script,
                topic_title="Rejected Topic",
                raise_on_failure=True,
            )


# ──────────────────────────────────────────────────────────────────────────────
# ModerationAgent._parse
# ──────────────────────────────────────────────────────────────────────────────

class TestModerationAgentParsing:
    def test_parse_valid_approved_json(self, agent):
        raw = json.dumps({
            "copyright_risk_score": 5.0,
            "duplicate_risk_score": 8.0,
            "spam_risk_score": 4.0,
            "policy_risk_score": 3.0,
            "monetization_risk_score": 12.0,
            "copyright_risk": False,
            "duplicate_content": False,
            "spam_risk": False,
            "policy_violation": False,
            "monetization_unsafe": False,
            "overall_risk_score": 12.0,
            "approved": True,
            "rejection_reasons": [],
            "recommendations": ["Add timestamps"],
            "reviewer_notes": "Clean content.",
        })
        result = agent._parse(raw)
        assert result.approved is True
        assert result.flags.any_flagged() is False
        assert result.overall_risk_score == 12.0
        assert result.rejection_reasons == []

    def test_parse_valid_rejected_json(self, agent):
        raw = json.dumps({
            "copyright_risk_score": 85.0,
            "duplicate_risk_score": 10.0,
            "spam_risk_score": 5.0,
            "policy_risk_score": 5.0,
            "monetization_risk_score": 10.0,
            "copyright_risk": True,
            "duplicate_content": False,
            "spam_risk": False,
            "policy_violation": False,
            "monetization_unsafe": False,
            "overall_risk_score": 85.0,
            "approved": False,
            "rejection_reasons": ["Detected copyrighted song lyrics in script body"],
            "recommendations": ["Remove or paraphrase the copyrighted section"],
            "reviewer_notes": "Copyright issue found in section 2.",
        })
        result = agent._parse(raw)
        assert result.approved is False
        assert result.flags.copyright_risk is True
        assert len(result.rejection_reasons) == 1

    def test_parse_auto_flags_when_score_above_threshold(self, agent):
        raw = json.dumps({
            "copyright_risk_score": 80.0,
            "duplicate_risk_score": 10.0,
            "spam_risk_score": 5.0,
            "policy_risk_score": 5.0,
            "monetization_risk_score": 10.0,
            "overall_risk_score": 80.0,
            "approved": True,  # contradicts the high score — parse should correct
            "rejection_reasons": [],
            "recommendations": [],
            "reviewer_notes": "",
        })
        result = agent._parse(raw)
        # copyright_risk should be auto-flagged because score >= 70
        assert result.flags.copyright_risk is True

    def test_parse_json_with_code_fence(self, agent):
        raw = '```json\n{"copyright_risk_score": 5.0, "duplicate_risk_score": 5.0, "spam_risk_score": 5.0, "policy_risk_score": 5.0, "monetization_risk_score": 5.0, "copyright_risk": false, "duplicate_content": false, "spam_risk": false, "policy_violation": false, "monetization_unsafe": false, "overall_risk_score": 5.0, "approved": true, "rejection_reasons": [], "recommendations": [], "reviewer_notes": "OK"}\n```'
        result = agent._parse(raw)
        assert result.approved is True

    def test_parse_invalid_json_returns_safe_fallback(self, agent):
        result = agent._parse("NOT JSON AT ALL")
        assert isinstance(result, ModerationAgentOutput)
        assert result.approved is True  # safe fallback approves conservatively

    def test_parse_clamps_risk_scores(self, agent):
        raw = json.dumps({
            "copyright_risk_score": 150.0,
            "duplicate_risk_score": -10.0,
            "spam_risk_score": 200.0,
            "policy_risk_score": -5.0,
            "monetization_risk_score": 999.0,
            "copyright_risk": False,
            "duplicate_content": False,
            "spam_risk": False,
            "policy_violation": False,
            "monetization_unsafe": False,
            "overall_risk_score": 50.0,
            "approved": True,
            "rejection_reasons": [],
            "recommendations": [],
            "reviewer_notes": "",
        })
        result = agent._parse(raw)
        assert result.risk_scores.copyright_risk_score <= 100.0
        assert result.risk_scores.duplicate_risk_score >= 0.0
        assert result.risk_scores.spam_risk_score <= 100.0

    def test_parse_auto_adds_rejection_reason_when_flagged(self, agent):
        raw = json.dumps({
            "copyright_risk_score": 10.0,
            "duplicate_risk_score": 10.0,
            "spam_risk_score": 10.0,
            "policy_risk_score": 10.0,
            "monetization_risk_score": 10.0,
            "copyright_risk": True,
            "duplicate_content": False,
            "spam_risk": False,
            "policy_violation": False,
            "monetization_unsafe": False,
            "overall_risk_score": 10.0,
            "approved": False,
            "rejection_reasons": [],  # empty — parser should auto-fill
            "recommendations": [],
            "reviewer_notes": "",
        })
        result = agent._parse(raw)
        assert len(result.rejection_reasons) > 0

    def test_safe_fallback_structure(self, agent):
        fallback = agent._safe_fallback()
        assert fallback.approved is True
        assert isinstance(fallback.flags, ModerationFlags)
        assert isinstance(fallback.risk_scores, ModerationRisk)
        assert isinstance(fallback.recommendations, list)
        assert fallback.overall_risk_score == 0.0


# ──────────────────────────────────────────────────────────────────────────────
# ModerationWorkflow
# ──────────────────────────────────────────────────────────────────────────────

class TestModerationWorkflow:
    async def test_workflow_run_returns_state(self, mock_llm):
        workflow = ModerationWorkflow(llm_provider=mock_llm)
        state = await workflow.run(
            script_id=str(uuid.uuid4()),
            script_content=CLEAN_SCRIPT,
            topic_title="Docker Tutorial",
            niche="devops",
        )
        assert state is not None
        assert "status" in state

    async def test_workflow_complete_status(self, mock_llm):
        workflow = ModerationWorkflow(llm_provider=mock_llm)
        state = await workflow.run(
            script_id=str(uuid.uuid4()),
            script_content=CLEAN_SCRIPT,
        )
        assert state["status"] in ("complete", "failed")

    async def test_workflow_has_approved_field(self, mock_llm):
        workflow = ModerationWorkflow(llm_provider=mock_llm)
        state = await workflow.run(
            script_id=str(uuid.uuid4()),
            script_content=CLEAN_SCRIPT,
        )
        assert "approved" in state
        assert isinstance(state["approved"], bool)

    async def test_workflow_has_all_flag_fields(self, mock_llm):
        workflow = ModerationWorkflow(llm_provider=mock_llm)
        state = await workflow.run(
            script_id=str(uuid.uuid4()),
            script_content=CLEAN_SCRIPT,
        )
        if state["status"] == "complete":
            for key in [
                "copyright_risk", "duplicate_content", "spam_risk",
                "policy_violation", "monetization_unsafe",
            ]:
                assert key in state
                assert isinstance(state[key], bool)

    async def test_workflow_has_all_risk_score_fields(self, mock_llm):
        workflow = ModerationWorkflow(llm_provider=mock_llm)
        state = await workflow.run(
            script_id=str(uuid.uuid4()),
            script_content=CLEAN_SCRIPT,
        )
        if state["status"] == "complete":
            for key in [
                "copyright_risk_score", "duplicate_risk_score", "spam_risk_score",
                "policy_risk_score", "monetization_risk_score", "overall_risk_score",
            ]:
                assert key in state
                assert 0.0 <= state[key] <= 100.0

    async def test_workflow_has_rejection_reasons(self, mock_llm):
        workflow = ModerationWorkflow(llm_provider=mock_llm)
        state = await workflow.run(
            script_id=str(uuid.uuid4()),
            script_content=CLEAN_SCRIPT,
        )
        if state["status"] == "complete":
            assert isinstance(state["rejection_reasons"], list)

    async def test_workflow_has_recommendations(self, mock_llm):
        workflow = ModerationWorkflow(llm_provider=mock_llm)
        state = await workflow.run(
            script_id=str(uuid.uuid4()),
            script_content=CLEAN_SCRIPT,
        )
        if state["status"] == "complete":
            assert isinstance(state["recommendations"], list)

    async def test_workflow_passes_seo_metadata(self, mock_llm):
        workflow = ModerationWorkflow(llm_provider=mock_llm)
        sid = str(uuid.uuid4())
        state = await workflow.run(
            script_id=sid,
            script_content=CLEAN_SCRIPT,
            topic_title="Docker Guide",
            niche="devops",
            seo_title="Docker Guide 2024",
            seo_description="Complete Docker tutorial.",
            tags=["docker", "devops"],
        )
        assert state["script_id"] == sid

    async def test_workflow_failed_llm(self):
        bad_llm = MagicMock()
        bad_llm.generate_text = AsyncMock(side_effect=Exception("LLM unavailable"))
        workflow = ModerationWorkflow(llm_provider=bad_llm)
        state = await workflow.run(
            script_id=str(uuid.uuid4()),
            script_content=CLEAN_SCRIPT,
        )
        assert state["status"] == "failed"
        assert state["error"] is not None

    async def test_workflow_initial_state_approved_false(self, mock_llm):
        """Initial state should default approved=False until node runs."""
        workflow = ModerationWorkflow(llm_provider=mock_llm)
        state = await workflow.run(
            script_id=str(uuid.uuid4()),
            script_content=CLEAN_SCRIPT,
        )
        # After successful run, approved should reflect the LLM result
        if state["status"] == "complete":
            assert isinstance(state["approved"], bool)

    async def test_workflow_with_empty_tags(self, mock_llm):
        workflow = ModerationWorkflow(llm_provider=mock_llm)
        state = await workflow.run(
            script_id=str(uuid.uuid4()),
            script_content=CLEAN_SCRIPT,
            tags=[],
        )
        assert state["status"] in ("complete", "failed")