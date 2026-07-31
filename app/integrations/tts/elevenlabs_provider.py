import asyncio
import math
import wave
from pathlib import Path
from typing import Optional


class ElevenLabsProvider:
    def __init__(self, voice: str = "alloy", style: str = "narration", sample_rate: int = 24000):
        self.voice = voice
        self.style = style
        self.sample_rate = sample_rate

    async def synthesize_speech(self, text: str, output_path: str) -> str:
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(self._write_wave, output_file, text, self.sample_rate, 180)
        return str(output_file)

    def _write_wave(self, path: Path, text: str, sample_rate: int, frequency: int) -> None:
        duration_secs = max(1.0, min(12.0, len(text) * 0.05))
        frame_count = int(sample_rate * duration_secs)
        amplitude = 0.45 * 32767

        with wave.open(str(path), "wb") as wave_file:
            wave_file.setnchannels(1)
            wave_file.setsampwidth(2)
            wave_file.setframerate(sample_rate)
            frames = bytearray()
            for i in range(frame_count):
                sample = int(amplitude * math.sin(2 * math.pi * frequency * i / sample_rate))
                frames.extend(sample.to_bytes(2, "little", signed=True))
            wave_file.writeframes(frames)
