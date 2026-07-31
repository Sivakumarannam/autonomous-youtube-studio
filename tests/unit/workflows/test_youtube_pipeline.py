import asyncio

from app.workflows.youtube_pipeline import YouTubePipeline
from app.llm_providers.mock_provider import MockLLMProvider


def test_youtube_pipeline_runs():
    pipeline = YouTubePipeline(MockLLMProvider())
    state = asyncio.run(pipeline.run("Docker vs Kubernetes", "A quick comparison"))

    assert state["status"] in {"complete", "failed"}
    assert state["topic_title"] == "Docker vs Kubernetes"
