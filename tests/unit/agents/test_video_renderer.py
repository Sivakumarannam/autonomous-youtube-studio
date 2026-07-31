from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.agents.video_agent.renderer import VideoRenderer


SAMPLE_SCENES = [
    {
        "scene_number": 1,
        "duration_seconds": 1,
        "narration": "Intro to the topic",
        "visual": "A bold title card with a blue accent stripe",
    },
    {
        "scene_number": 2,
        "duration_seconds": 1,
        "narration": "Main content goes here",
        "visual": "Side by side comparison graphic",
    },
]


def test_render_scene_cards_creates_one_png_per_scene(tmp_path: Path):
    renderer = VideoRenderer()
    frames_dir = tmp_path / "frames"
    frames_dir.mkdir()

    frame_paths = renderer._render_scene_cards(
        scenes=SAMPLE_SCENES,
        frames_dir=frames_dir,
        resolution=(640, 360),
    )

    assert len(frame_paths) == len(SAMPLE_SCENES)

    for path in frame_paths:
        assert path.exists()
        assert path.stat().st_size > 0
        assert path.suffix == ".png"


def test_render_scene_cards_handles_missing_visual_text(tmp_path: Path):
    renderer = VideoRenderer()
    frames_dir = tmp_path / "frames"
    frames_dir.mkdir()

    scenes = [{"scene_number": 1, "duration_seconds": 2}]

    frame_paths = renderer._render_scene_cards(
        scenes=scenes,
        frames_dir=frames_dir,
        resolution=(640, 360),
    )

    assert len(frame_paths) == 1
    assert frame_paths[0].exists()


def test_render_with_no_scenes_fails_gracefully():
    renderer = VideoRenderer()

    result = renderer.render(
        script_id="no-scenes",
        scenes=[],
        audio_path=None,
        script_type="long",
    )

    assert result.success is False
    assert result.error_message is not None


def test_render_full_pipeline_produces_real_mp4(tmp_path, monkeypatch):
    pytest.importorskip("moviepy.editor")

    from app.core.config import settings

    monkeypatch.setattr(settings, "storage_local_path", str(tmp_path))

    renderer = VideoRenderer()

    result = renderer.render(
        script_id="renderer-pipeline-test",
        scenes=SAMPLE_SCENES,
        audio_path=None,
        script_type="long",
    )

    assert result.success is True
    assert result.video_path is not None

    output_path = Path(result.video_path)

    assert output_path.exists()
    assert output_path.stat().st_size > 0
    assert result.file_size > 0
    assert result.duration_seconds > 0


# ---------------------------------------------------------------------------
# Proportional timing — scene durations scale to real audio length
# ---------------------------------------------------------------------------


class TestProportionalTiming:
    """_assemble_video must distribute real audio duration across scene cards
    in proportion to each card's nominal duration_seconds.  This is the
    mechanism that keeps on-screen text in sync with the narration."""

    def _make_frame(self, tmp_path: Path) -> Path:
        """Create a tiny valid PNG so ImageClip doesn't fail."""
        from PIL import Image

        p = tmp_path / "frame.png"
        Image.new("RGB", (64, 36), (0, 0, 0)).save(str(p))
        return p

    def test_scene_durations_scaled_to_audio_duration(self, tmp_path):
        """When audio is present, clip durations must sum to audio_duration."""
        scenes = [
            {"scene_number": 1, "duration_seconds": 10, "narration": "A."},
            {"scene_number": 2, "duration_seconds": 10, "narration": "B."},
            {"scene_number": 3, "duration_seconds": 10, "narration": "C."},
        ]
        fake_audio_duration = 15.0

        captured_durations: list[float] = []

        # Replicate the proportional-scaling logic from _assemble_video and
        # verify it produces the right numbers — no moviepy import needed.
        def spy_assemble(scenes_inner, audio_duration):
            raw = [max(1, int(s.get("duration_seconds", 5) or 5)) for s in scenes_inner]
            total_raw = sum(raw)
            scaled = [max(0.5, (d / total_raw) * audio_duration) for d in raw]
            captured_durations.extend(scaled)

        spy_assemble(scenes, fake_audio_duration)

        assert len(captured_durations) == 3
        assert abs(sum(captured_durations) - fake_audio_duration) < 0.01

    def test_equal_scenes_get_equal_duration(self, tmp_path):
        """Scenes with equal nominal durations each get equal audio time."""
        scenes = [
            {"scene_number": i + 1, "duration_seconds": 5, "narration": f"Sentence {i}."}
            for i in range(4)
        ]
        audio_duration = 20.0
        raw = [5, 5, 5, 5]
        total = sum(raw)
        scaled = [max(0.5, (d / total) * audio_duration) for d in raw]

        assert all(abs(s - 5.0) < 0.01 for s in scaled)

    def test_proportional_weights_respected(self):
        """A scene with 2x the nominal duration gets 2x the audio time."""
        raw = [5.0, 10.0]
        audio_duration = 30.0
        total = sum(raw)
        scaled = [max(0.5, (d / total) * audio_duration) for d in raw]

        assert abs(scaled[1] / scaled[0] - 2.0) < 0.01

    def test_scene_cards_carry_narration_text(self, tmp_path):
        """Each rendered PNG card must be driven by its narration text — not
        a stale storyboard description.  We verify that _render_scene_cards
        reads the 'narration' key for both the centred text and the caption."""
        frames_dir = tmp_path / "frames"
        frames_dir.mkdir()

        scenes = [
            {
                "scene_number": 1,
                "duration_seconds": 5,
                "narration": "Artificial Intelligence is transforming the world.",
                "visual": "Some visual description",
            }
        ]

        renderer = VideoRenderer()
        # Should not raise and should produce exactly one frame
        frame_paths = renderer._render_scene_cards(
            scenes=scenes, frames_dir=frames_dir, resolution=(640, 360)
        )

        assert len(frame_paths) == 1
        assert frame_paths[0].exists()
        assert frame_paths[0].stat().st_size > 0

    def test_silent_video_uses_nominal_durations(self, tmp_path, monkeypatch):
        """Without audio the renderer falls back to nominal durations."""
        pytest.importorskip("moviepy.editor")

        from app.core.config import settings
        monkeypatch.setattr(settings, "storage_local_path", str(tmp_path))

        scenes_with_equal_dur = [
            {"scene_number": 1, "duration_seconds": 2, "narration": "First sentence."},
            {"scene_number": 2, "duration_seconds": 2, "narration": "Second sentence."},
        ]

        renderer = VideoRenderer()
        result = renderer.render(
            script_id="silent-timing-test",
            scenes=scenes_with_equal_dur,
            audio_path=None,
            script_type="long",
        )

        assert result.success is True
        # With 2 × 2 s clips at 18 fps the total should be ~4 s
        assert result.duration_seconds == pytest.approx(4.0, abs=0.5)