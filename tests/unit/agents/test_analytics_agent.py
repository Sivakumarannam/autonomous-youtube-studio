import asyncio

from app.agents.analytics_agent.agent import AnalyticsAgent
from app.llm_providers.mock_provider import MockLLMProvider


def test_analytics_agent_generates_report():
    agent = AnalyticsAgent(MockLLMProvider())
    output = asyncio.run(agent.generate_report("Docker vs Kubernetes", views=1200, likes=60, comments=20))

    assert output.success is True
    assert output.summary
    assert output.recommendations
