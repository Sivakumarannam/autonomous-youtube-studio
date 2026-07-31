"""Targeted tests for VideoRenderer image-compositing path.

Covers _make_background (cover crop) and _render_scene_cards with image_paths.
No real video encoding — PIL and frame generation only.
"""
from __future__ import annotations

import io
from pathlib import Path
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_pil_jpeg(width: int = 800, height: int = 600) -> bytes:
    """Return minimal valid JPEG bytes via PIL."""
    from PIL import Image

    buf = io.BytesIO()
    img = Image.new("RGB", (width, height), (120, 80, 200))
    img.save(buf, "JPEG")
    return buf.getvalue()


def _make_scene(
    scene_number: int = 1,
    narration: str = "Hello world",
    visual: str = "wide shot of mountains",
) -> dict:
    return {
        "scene_number": scene_number,
        "timestamp": "0:00",
        "duration_seconds": 5.0,
        "narration": narration,
        "visual": visual,
    }


# ---------------------------------------------------------------------------
# _make_background — unit tests
# ---------------------------------------------------------------------------

class TestMakeBackground:
    def test_solid_fallback_when_no_path(self):
        from app.agents.video_agent.renderer import VideoRenderer
        from PIL import Image

        renderer = VideoRenderer()
        img = renderer._make_background(
            bg_image_path=None,
            width=320,
            height=240,
            fallback_color=(10, 20, 30),
        )
        assert img.size == (320, 240)
        assert img.mode == "RGB"
        # Top-left pixel should be the fallback colour
        assert img.getpixel((0, 0)) == (10, 20, 30)

    def test_solid_fallback_when_path_is_missing_file(self, tmp_path):
        from app.agents.video_agent.renderer import VideoRenderer

        renderer = VideoRenderer()
        missing = str(tmp_path / "does_not_exist.jpg")
        img = renderer._make_background(
            bg_image_path=missing,
            width=320,
            height=240,
            fallback_color=(5, 5, 5),
        )
        assert img.size == (320, 240)
        assert img.getpixel((0, 0)) == (5, 5, 5)

    def test_ai_image_resized_to_canvas(self, tmp_path):
        """A small source image should be upscaled to fill the canvas."""
        from app.agents.video_agent.renderer import VideoRenderer

        jpeg_bytes = _make_pil_jpeg(width=200, height=150)
        img_file = tmp_path / "bg.jpg"
        img_file.write_bytes(jpeg_bytes)

        renderer = VideoRenderer()
        result = renderer._make_background(
            bg_image_path=str(img_file),
            width=640,
            height=360,
            fallback_color=(0, 0, 0),
        )
        assert result.size == (640, 360)

    def test_ai_image_wide_portrait_cropped_to_landscape(self, tmp_path):
        """Portrait source should be cropped (not stretched) to landscape canvas."""
        from app.agents.video_agent.renderer import VideoRenderer

        # 200×800 portrait → must fill 720×1280 landscape without distortion
        jpeg_bytes = _make_pil_jpeg(width=200, height=800)
        img_file = tmp_path / "portrait.jpg"
        img_file.write_bytes(jpeg_bytes)

        renderer = VideoRenderer()
        result = renderer._make_background(
            bg_image_path=str(img_file),
            width=1280,
            height=720,
            fallback_color=(0, 0, 0),
        )
        assert result.size == (1280, 720)

    def test_corrupt_image_falls_back_to_solid(self, tmp_path):
        """A file that is not a valid image must silently fall through."""
        from app.agents.video_agent.renderer import VideoRenderer

        bad_file = tmp_path / "bad.jpg"
        bad_file.write_bytes(b"this is not an image")

        renderer = VideoRenderer()
        img = renderer._make_background(
            bg_image_path=str(bad_file),
            width=320,
            height=240,
            fallback_color=(99, 99, 99),
        )
        assert img.size == (320, 240)
        assert img.getpixel((0, 0)) == (99, 99, 99)


# ---------------------------------------------------------------------------
# _render_scene_cards — integration tests with image_paths
# ---------------------------------------------------------------------------

class TestRenderSceneCards:
    def test_frame_written_for_each_scene(self, tmp_path):
        from app.agents.video_agent.renderer import VideoRenderer

        renderer = VideoRenderer()
        scenes = [_make_scene(i + 1) for i in range(3)]
        frames_dir = tmp_path / "frames"
        frames_dir.mkdir()

        paths = renderer._render_scene_cards(
            scenes=scenes,
            frames_dir=frames_dir,
            resolution=(640, 360),
            image_paths={},
        )

        assert len(paths) == 3
        for p in paths:
            assert p.exists()

    def test_scene_with_valid_image_path_uses_ai_background(self, tmp_path):
        """When image_paths provides a valid file, _make_background is called
        with that path (not None) for that scene."""
        from app.agents.video_agent.renderer import VideoRenderer

        jpeg_bytes = _make_pil_jpeg(width=800, height=600)
        img_file = tmp_path / "scene1.jpg"
        img_file.write_bytes(jpeg_bytes)

        renderer = VideoRenderer()
        call_log: list[dict] = []
        original_make_bg = renderer._make_background

        def spy_make_background(**kwargs):
            call_log.append(kwargs)
            return original_make_bg(**kwargs)

        renderer._make_background = spy_make_background  # type: ignore[method-assign]

        frames_dir = tmp_path / "frames"
        frames_dir.mkdir()
        renderer._render_scene_cards(
            scenes=[_make_scene(scene_number=1)],
            frames_dir=frames_dir,
            resolution=(640, 360),
            image_paths={1: str(img_file)},
        )

        assert len(call_log) == 1
        assert call_log[0]["bg_image_path"] == str(img_file)

    def test_scene_without_image_path_uses_fallback_color(self, tmp_path):
        """Scenes not in image_paths must receive bg_image_path=None."""
        from app.agents.video_agent.renderer import VideoRenderer

        renderer = VideoRenderer()
        call_log: list[dict] = []
        original = renderer._make_background

        def spy(**kwargs):
            call_log.append(kwargs)
            return original(**kwargs)

        renderer._make_background = spy  # type: ignore[method-assign]

        frames_dir = tmp_path / "frames"
        frames_dir.mkdir()
        renderer._render_scene_cards(
            scenes=[_make_scene(scene_number=2)],
            frames_dir=frames_dir,
            resolution=(640, 360),
            image_paths={},  # scene 2 not present
        )

        assert call_log[0]["bg_image_path"] is None

    def test_missing_image_file_does_not_abort_render(self, tmp_path):
        """A broken path in image_paths must not raise; render completes."""
        from app.agents.video_agent.renderer import VideoRenderer

        renderer = VideoRenderer()
        frames_dir = tmp_path / "frames"
        frames_dir.mkdir()

        paths = renderer._render_scene_cards(
            scenes=[_make_scene(scene_number=1), _make_scene(scene_number=2)],
            frames_dir=frames_dir,
            resolution=(640, 360),
            image_paths={1: str(tmp_path / "ghost.jpg")},  # file does not exist
        )

        # Both frames must be written regardless
        assert len(paths) == 2
        assert all(p.exists() for p in paths)

    def test_no_image_paths_arg_is_equivalent_to_empty_dict(self, tmp_path):
        """Calling _render_scene_cards without image_paths must work (default)."""
        from app.agents.video_agent.renderer import VideoRenderer

        renderer = VideoRenderer()
        frames_dir = tmp_path / "frames"
        frames_dir.mkdir()

        paths = renderer._render_scene_cards(
            scenes=[_make_scene(1), _make_scene(2)],
            frames_dir=frames_dir,
            resolution=(640, 360),
            # image_paths omitted intentionally
        )
        assert len(paths) == 2


# ---------------------------------------------------------------------------
# render() public API — image_paths wired end-to-end
# ---------------------------------------------------------------------------

class TestRenderPublicApi:
    def test_render_accepts_image_paths_without_error(self, tmp_path, monkeypatch):
        """render() must pass image_paths down without breaking the contract."""
        monkeypatch.setattr(
            "app.core.config.settings.storage_local_path", str(tmp_path)
        )
        from app.agents.video_agent.renderer import VideoRenderer

        jpeg_bytes = _make_pil_jpeg(800, 600)
        img_file = tmp_path / "bg1.jpg"
        img_file.write_bytes(jpeg_bytes)

        renderer = VideoRenderer()

        # Stub _assemble_video so we don't need ffmpeg
        renderer._assemble_video = lambda **kw: (5.0, 12345)  # type: ignore

        result = renderer.render(
            script_id="test-render-001",
            scenes=[_make_scene(1), _make_scene(2)],
            audio_path=None,
            script_type="long",
            image_paths={1: str(img_file)},
        )

        assert result.success is True

    def test_render_without_image_paths_arg_still_works(self, tmp_path, monkeypatch):
        """Existing callers that don't pass image_paths must be unaffected."""
        monkeypatch.setattr(
            "app.core.config.settings.storage_local_path", str(tmp_path)
        )
        from app.agents.video_agent.renderer import VideoRenderer

        renderer = VideoRenderer()
        renderer._assemble_video = lambda **kw: (3.0, 9999)  # type: ignore

        result = renderer.render(
            script_id="test-render-002",
            scenes=[_make_scene(1)],
            audio_path=None,
            script_type="short",
        )

        assert result.success is True
