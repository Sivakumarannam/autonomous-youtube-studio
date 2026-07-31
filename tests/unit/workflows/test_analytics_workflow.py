import asyncio

from app.workflows.analytics_workflow import AnalyticsWorkflow
from app.llm_providers.mock_provider import MockLLMProvider


def test_analytics_workflow_runs():
    workflow = AnalyticsWorkflow(MockLLMProvider())
    state = asyncio.run(workflow.run("Docker vs Kubernetes", views=1200, likes=60, comments=20))

    assert state["status"] in {"complete", "failed"}
    assert state["topic_title"] == "Docker vs Kubernetes"
