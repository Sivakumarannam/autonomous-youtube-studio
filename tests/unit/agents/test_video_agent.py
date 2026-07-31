import asyncio

from app.agents.video_agent.agent import VideoAgent
from app.llm_providers.mock_provider import MockLLMProvider


def test_video_agent_generates_plan():
    agent = VideoAgent(MockLLMProvider())
    output = asyncio.run(agent.generate_plan("Docker vs Kubernetes", "A quick comparison", script_type="long"))

    assert output.success is True
    assert output.scene_count > 0
    assert output.edits is not None
