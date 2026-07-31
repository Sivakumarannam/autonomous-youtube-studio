from pydantic import BaseModel, Field


class VoiceSettings(BaseModel):
    language: str = Field(default="en", description="BCP-47 language code, e.g. 'en', 'en-us'")
    speed: float = Field(default=1.0, ge=0.5, le=2.0, description="Speaking rate multiplier")
    pitch: float = Field(default=0.0, ge=-10.0, le=10.0, description="Pitch shift in semitones")
    volume: float = Field(default=1.0, ge=0.1, le=2.0, description="Volume multiplier")
    provider: str = Field(
        default="auto",
        description=(
            "TTS provider: auto | kokoro | piper | gtts | pyttsx3 | mock. "
            "'auto' tries kokoro → gtts → pyttsx3 in order."
        ),
    )
    gender: str = Field(
        default="female",
        description="Narrator gender: 'female' or 'male'. Controls voice selection for Kokoro/Piper.",
    )


class VoiceAgentInput(BaseModel):
    script_id: str
    script_content: str
    script_type: str = "long"    # "short" | "long"
    voice_settings: VoiceSettings = Field(default_factory=VoiceSettings)


class VoiceAgentOutput(BaseModel):
    audio_file_path: str = Field(..., description="Path to the generated MP3 file")
    duration_seconds: float = Field(default=0.0, ge=0.0, description="Estimated audio duration")
    word_count: int = Field(default=0, ge=0)
    provider_used: str = Field(default="", description="TTS provider that rendered the audio")
    language: str = Field(default="en")
    file_size_bytes: int = Field(default=0, ge=0)
    success: bool = Field(default=True)
    error_message: str | None = Field(default=None)