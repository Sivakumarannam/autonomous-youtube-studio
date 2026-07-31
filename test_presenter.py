import asyncio
from app.integrations.tts.edge_tts_provider import EdgeTTSProvider
from app.integrations.presenter_service import PresenterService

from dotenv import load_dotenv

load_dotenv()

import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import asyncio
from app.integrations.tts.edge_tts_provider import EdgeTTSProvider
from app.integrations.presenter_service import PresenterService
# ...rest unchanged

async def test():
    # Step 1: create a real (dummy tone) audio file to test with
    tts = EdgeTTSProvider()
    audio_path = await tts.synthesize_speech(
        "Hello, this is a test of the presenter service.",
        "test_audio.wav",
    )
    print("Audio created at:", audio_path)

    # Step 2: call the presenter service with that real file
    svc = PresenterService()
    out = await svc.generate(audio_path, "test_output.mp4")
    print("Result:", out)

asyncio.run(test())