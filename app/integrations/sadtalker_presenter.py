"""
SadTalkerPresenter — free lip-sync via a hosted SadTalker Gradio Space
on Hugging Face (kevinwang676/SadTalker by default).

Free because Hugging Face runs the GPU/CPU themselves as a public demo
— but it's shared public infrastructure, so it can queue behind other
users, and the specific Space it depends on can go down or change its
API at any time (a different owner's demo, not a guaranteed service).

IMPORTANT version pin: the default Space still runs old Gradio 3.x,
which only speaks the legacy `ws` protocol. gradio_client >=1.0
dropped `ws` support entirely (SSE-only). requirements.txt pins
gradio_client==0.16.4 for this reason — do not upgrade it unless you
point PRESENTER_HF_SPACE at a Space confirmed to run modern Gradio 4.x+.

If you ever swap PRESENTER_HF_SPACE for a different Space, re-run
`python inspect_space_api.py` first — argument names/order/count are
NOT standardized across SadTalker duplicates (confirmed by trial and
error: the official Space uses a different 16-arg named `/predict`
endpoint than this 8-arg unnamed one).
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Optional

from app.core.logging import get_logger

logger = get_logger(__name__)

# Verified via `client.view_api()` against kevinwang676/SadTalker on
# 2026-07-15 — single UNNAMED endpoint (fn_index=0), 8 args.
_STILL_MODE = True
_PREPROCESS_TYPE = "full"
_ENHANCER = False
_BATCH_SIZE = 1
_FACE_MODEL_RESOLUTION = "256"  # Radio option — a string, not an int
_POSE_STYLE = 0


class SadTalkerPresenter:
    """Facade for AI avatar generation via a hosted SadTalker Gradio Space."""

    def __init__(self) -> None:
        self._client = None  # lazily created, reused across calls

    def _space_id(self) -> str:
        from app.core.config import settings
        return getattr(settings, "presenter_hf_space", "") or os.environ.get(
            "PRESENTER_HF_SPACE", "kevinwang676/SadTalker"
        )

    def _hf_token(self) -> Optional[str]:
        from app.core.config import settings
        token = getattr(settings, "presenter_hf_token", "") or os.environ.get(
            "PRESENTER_HF_TOKEN", ""
        )
        return token or None

    def _get_client(self):
        if self._client is not None:
            return self._client

        import inspect
        from gradio_client import Client

        space_id = self._space_id()
        token = self._hf_token()
        logger.info("SadTalker: connecting to Hugging Face Space", space=space_id)

        if token:
            # gradio_client renamed this constructor kwarg from
            # `hf_token` to `token` between versions — detect which one
            # the installed version actually accepts.
            accepted = inspect.signature(Client.__init__).parameters
            if "token" in accepted:
                self._client = Client(space_id, token=token)
            elif "hf_token" in accepted:
                self._client = Client(space_id, hf_token=token)
            else:
                self._client = Client(space_id)
        else:
            self._client = Client(space_id)

        return self._client

    @staticmethod
    def _wrap_file(path: str):
        """
        gradio_client added the handle_file() wrapper for file-type
        inputs in a later version than what we're pinned to (0.16.4).
        Support both transparently.
        """
        try:
            from gradio_client import handle_file
            return handle_file(path)
        except ImportError:
            return path

    def generate(self, image_path: str, audio_path: str, output_path: str) -> Optional[str]:
        """
        Blocking call — the caller (PresenterService) is responsible for
        running this via asyncio.to_thread. Returns output_path on
        success, raises on failure (caller catches broadly).
        """
        client = self._get_client()
        result_path = client.predict(
            self._wrap_file(image_path),
            self._wrap_file(audio_path),
            _PREPROCESS_TYPE,
            _STILL_MODE,
            _ENHANCER,
            _BATCH_SIZE,
            _FACE_MODEL_RESOLUTION,
            _POSE_STYLE,
            fn_index=0,
        )

        if not result_path or not Path(result_path).exists():
            raise RuntimeError(f"SadTalker Space returned no usable output: {result_path!r}")

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(result_path, output_path)
        return output_path
