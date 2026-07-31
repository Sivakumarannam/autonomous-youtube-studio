import asyncio

from app.agents.upload_agent.agent import UploadAgent
from app.agents.upload_agent.models import UploadSettings
from app.llm_providers.mock_provider import MockLLMProvider


def test_upload_agent_prepares_upload_payload():
    agent = UploadAgent(MockLLMProvider())
    output = asyncio.run(agent.prepare_upload("Docker vs Kubernetes", "A comparison video", settings=UploadSettings(provider="mock")))

    assert output.success is True
    assert output.video_title
    assert output.status in {"queued", "ready"}
