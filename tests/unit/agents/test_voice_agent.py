import asyncio
from pathlib import Path

from app.agents.voice_agent.agent import VoiceAgent
from app.agents.voice_agent.models import VoiceSettings
from app.llm_providers.mock_provider import MockLLMProvider


def test_voice_agent_generates_audio():
    agent = VoiceAgent(MockLLMProvider())

    output = asyncio.run(
        agent.synthesise(
            script_content="""
            Welcome to our autonomous YouTube Studio.
            Today we'll compare Docker and Kubernetes.
            Stay until the end for the final verdict.
            """,
            script_id="voice-test",
            script_type="long",
            voice_settings=VoiceSettings(provider="mock"),
        )
    )

    assert output.success is True
    assert output.audio_file_path.endswith(".mp3")
    assert output.provider_used == "mock"
    assert output.duration_seconds > 0
    assert output.word_count > 0
    assert output.file_size_bytes > 0
    assert Path(output.audio_file_path).exists()


def test_voice_agent_short_script():
    agent = VoiceAgent(MockLLMProvider())

    output = asyncio.run(
        agent.synthesise(
            script_content="Docker is awesome.",
            script_id="short-script",
            script_type="short",
            voice_settings=VoiceSettings(provider="mock"),
        )
    )

    assert output.success
    assert output.word_count > 0
    assert output.duration_seconds > 0


def test_voice_agent_basic_cleanup():
    agent = VoiceAgent(MockLLMProvider())

    cleaned = agent._basic_clean(
        """
        ## Docker vs Kubernetes

        Visit:
        https://google.com

        **Bold Text**

        #DevOps
        """
    )

    assert "https://" not in cleaned
    assert "**" not in cleaned
    assert "#" not in cleaned


def test_voice_agent_mock_audio_created():
    agent = VoiceAgent(MockLLMProvider())

    output = asyncio.run(
        agent.synthesise(
            script_content="Testing mock audio generation.",
            script_id="mock-audio",
            voice_settings=VoiceSettings(provider="mock"),
        )
    )

    audio = Path(output.audio_file_path)

    assert audio.exists()
    assert audio.stat().st_size > 0