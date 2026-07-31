"""
Unit tests for the voice/scene synchronisation helpers introduced in
app.agents.video_agent.service.

All functions under test are pure (no DB, no async) so every test runs fast
and without any fixtures.
"""

import pytest

from app.agents.video_agent.service import align_sentences_to_scenes, split_sentences


# ---------------------------------------------------------------------------
# split_sentences
# ---------------------------------------------------------------------------


class TestSplitSentences:
    def test_splits_on_period(self):
        text = "Hello world. This is a test."
        result = split_sentences(text)
        assert result == ["Hello world.", "This is a test."]

    def test_splits_on_exclamation(self):
        text = "Amazing! Really great!"
        result = split_sentences(text)
        assert result == ["Amazing!", "Really great!"]

    def test_splits_on_question_mark(self):
        text = "What is AI? It is transformative."
        result = split_sentences(text)
        assert result == ["What is AI?", "It is transformative."]

    def test_mixed_punctuation(self):
        text = "Artificial Intelligence is transforming the world. Businesses are using AI to improve productivity. The future looks bright!"
        result = split_sentences(text)
        assert len(result) == 3
        assert result[0] == "Artificial Intelligence is transforming the world."
        assert result[1] == "Businesses are using AI to improve productivity."
        assert result[2] == "The future looks bright!"

    def test_single_sentence_no_boundary(self):
        text = "No punctuation here"
        result = split_sentences(text)
        assert result == ["No punctuation here"]

    def test_empty_string_returns_empty_list(self):
        assert split_sentences("") == []

    def test_whitespace_only_returns_empty_list(self):
        assert split_sentences("   ") == []

    def test_strips_surrounding_whitespace_from_each_sentence(self):
        text = "First sentence.  Second sentence."
        result = split_sentences(text)
        assert result[0] == "First sentence."
        assert result[1] == "Second sentence."

    def test_single_word(self):
        result = split_sentences("Hello")
        assert result == ["Hello"]

    def test_multiple_spaces_between_sentences(self):
        text = "Sentence one.   Sentence two."
        result = split_sentences(text)
        assert len(result) == 2


# ---------------------------------------------------------------------------
# align_sentences_to_scenes — equal count
# ---------------------------------------------------------------------------


class TestAlignEqual:
    """One sentence per storyboard scene — one-to-one mapping."""

    def test_one_sentence_one_scene(self):
        sentences = ["Only sentence."]
        scenes = [{"scene_number": 1, "duration_seconds": 10.0, "visual": "intro", "timestamp": "00:00"}]

        result = align_sentences_to_scenes(sentences, scenes)

        assert len(result) == 1
        assert result[0]["narration"] == "Only sentence."
        assert result[0]["duration_seconds"] == 10.0
        assert result[0]["visual"] == "intro"

    def test_two_sentences_two_scenes(self):
        sentences = ["First.", "Second."]
        scenes = [
            {"scene_number": 1, "duration_seconds": 5.0, "visual": "A", "timestamp": "00:00"},
            {"scene_number": 2, "duration_seconds": 8.0, "visual": "B", "timestamp": "00:05"},
        ]

        result = align_sentences_to_scenes(sentences, scenes)

        assert len(result) == 2
        assert result[0]["narration"] == "First."
        assert result[0]["duration_seconds"] == 5.0
        assert result[1]["narration"] == "Second."
        assert result[1]["duration_seconds"] == 8.0

    def test_narration_matches_spoken_text_exactly(self):
        """Screen text must be identical to what is spoken."""
        spoken = "Artificial Intelligence is transforming the world."
        sentences = [spoken]
        scenes = [{"scene_number": 1, "duration_seconds": 6.0, "visual": "globe", "timestamp": ""}]

        result = align_sentences_to_scenes(sentences, scenes)

        assert result[0]["narration"] == spoken


# ---------------------------------------------------------------------------
# align_sentences_to_scenes — more scenes than sentences (MERGE)
# ---------------------------------------------------------------------------


class TestAlignMoreScenesThanSentences:
    """Storyboard scenes are merged so each output card = one sentence."""

    def test_two_sentences_four_scenes(self):
        sentences = ["First sentence.", "Second sentence."]
        scenes = [
            {"scene_number": 1, "duration_seconds": 3.0, "visual": "V1", "timestamp": ""},
            {"scene_number": 2, "duration_seconds": 4.0, "visual": "V2", "timestamp": ""},
            {"scene_number": 3, "duration_seconds": 5.0, "visual": "V3", "timestamp": ""},
            {"scene_number": 4, "duration_seconds": 6.0, "visual": "V4", "timestamp": ""},
        ]

        result = align_sentences_to_scenes(sentences, scenes)

        assert len(result) == 2
        assert result[0]["narration"] == "First sentence."
        assert result[1]["narration"] == "Second sentence."

    def test_merged_duration_equals_sum_of_constituent_scenes(self):
        sentences = ["A.", "B."]
        scenes = [
            {"scene_number": 1, "duration_seconds": 3.0, "visual": "", "timestamp": ""},
            {"scene_number": 2, "duration_seconds": 7.0, "visual": "", "timestamp": ""},
            {"scene_number": 3, "duration_seconds": 5.0, "visual": "", "timestamp": ""},
            {"scene_number": 4, "duration_seconds": 5.0, "visual": "", "timestamp": ""},
        ]
        result = align_sentences_to_scenes(sentences, scenes)

        # 4 scenes / 2 sentences → each group has 2 scenes
        assert result[0]["duration_seconds"] == pytest.approx(10.0)  # 3+7
        assert result[1]["duration_seconds"] == pytest.approx(10.0)  # 5+5

    def test_uneven_merge_distributes_remainder_to_first_groups(self):
        """5 scenes / 2 sentences → group sizes 3 and 2."""
        sentences = ["First.", "Second."]
        scenes = [
            {"scene_number": i + 1, "duration_seconds": 2.0, "visual": "", "timestamp": ""}
            for i in range(5)
        ]
        result = align_sentences_to_scenes(sentences, scenes)

        assert len(result) == 2
        # First group gets 3 scenes (base=2, remainder=1 → sent 0 gets +1)
        assert result[0]["duration_seconds"] == pytest.approx(6.0)  # 3 × 2
        # Second group gets 2 scenes
        assert result[1]["duration_seconds"] == pytest.approx(4.0)  # 2 × 2

    def test_one_sentence_many_scenes_all_merged(self):
        sentences = ["The only sentence."]
        scenes = [
            {"scene_number": i + 1, "duration_seconds": 4.0, "visual": f"V{i}", "timestamp": ""}
            for i in range(6)
        ]
        result = align_sentences_to_scenes(sentences, scenes)

        assert len(result) == 1
        assert result[0]["narration"] == "The only sentence."
        assert result[0]["duration_seconds"] == pytest.approx(24.0)  # 6 × 4

    def test_visual_taken_from_first_scene_in_group(self):
        sentences = ["Sentence."]
        scenes = [
            {"scene_number": 1, "duration_seconds": 5.0, "visual": "First visual", "timestamp": ""},
            {"scene_number": 2, "duration_seconds": 5.0, "visual": "Second visual", "timestamp": ""},
        ]
        result = align_sentences_to_scenes(sentences, scenes)
        assert result[0]["visual"] == "First visual"

    def test_output_has_sequential_scene_numbers(self):
        sentences = ["A.", "B.", "C."]
        scenes = [
            {"scene_number": i + 1, "duration_seconds": 3.0, "visual": "", "timestamp": ""}
            for i in range(6)
        ]
        result = align_sentences_to_scenes(sentences, scenes)
        assert [r["scene_number"] for r in result] == [1, 2, 3]


# ---------------------------------------------------------------------------
# align_sentences_to_scenes — more sentences than scenes (DISTRIBUTE)
# ---------------------------------------------------------------------------


class TestAlignMoreSentencesThanScenes:
    """Each sentence becomes its own card; visual context is borrowed from the
    nearest storyboard scene.  This is the previously broken case."""

    def test_returns_one_card_per_sentence(self):
        sentences = ["S1.", "S2.", "S3.", "S4.", "S5."]
        scenes = [
            {"scene_number": 1, "duration_seconds": 10.0, "visual": "A", "timestamp": ""},
            {"scene_number": 2, "duration_seconds": 20.0, "visual": "B", "timestamp": ""},
        ]
        result = align_sentences_to_scenes(sentences, scenes)

        # Key invariant: exactly one card per sentence
        assert len(result) == 5

    def test_narration_matches_spoken_sentence_exactly(self):
        """The screen text must be the same as what is spoken — the core fix."""
        sentences = [
            "Artificial Intelligence is transforming the world.",
            "Businesses are using AI to improve productivity.",
        ]
        scenes = [
            {"scene_number": 1, "duration_seconds": 8.0, "visual": "globe", "timestamp": ""},
        ]
        result = align_sentences_to_scenes(sentences, scenes)

        assert len(result) == 2
        assert result[0]["narration"] == sentences[0]
        assert result[1]["narration"] == sentences[1]

    def test_total_duration_preserved_proportionally(self):
        """Sum of output durations should equal total storyboard duration."""
        sentences = ["A.", "B.", "C.", "D."]
        total = 20.0
        scenes = [{"scene_number": 1, "duration_seconds": total, "visual": "", "timestamp": ""}]

        result = align_sentences_to_scenes(sentences, scenes)

        assert len(result) == 4
        assert sum(r["duration_seconds"] for r in result) == pytest.approx(total)

    def test_all_cards_get_equal_duration_when_one_scene(self):
        sentences = ["A.", "B.", "C."]
        scenes = [{"scene_number": 1, "duration_seconds": 15.0, "visual": "", "timestamp": ""}]

        result = align_sentences_to_scenes(sentences, scenes)

        durations = [r["duration_seconds"] for r in result]
        assert all(d == pytest.approx(5.0) for d in durations)

    def test_visual_borrowed_from_nearest_storyboard_scene(self):
        """First sentences borrow from scene 0; later sentences borrow from scene 1."""
        sentences = ["S1.", "S2.", "S3.", "S4."]
        scenes = [
            {"scene_number": 1, "duration_seconds": 10.0, "visual": "Alpha", "timestamp": ""},
            {"scene_number": 2, "duration_seconds": 10.0, "visual": "Beta", "timestamp": ""},
        ]
        result = align_sentences_to_scenes(sentences, scenes)

        # sentence 0 → scene 0 (i=0, 0*2/4=0)
        assert result[0]["visual"] == "Alpha"
        # sentence 1 → scene 0 (i=1, 1*2/4=0)
        assert result[1]["visual"] == "Alpha"
        # sentence 2 → scene 1 (i=2, 2*2/4=1)
        assert result[2]["visual"] == "Beta"
        # sentence 3 → scene 1 (i=3, 3*2/4=1)
        assert result[3]["visual"] == "Beta"

    def test_sequential_scene_numbers_in_output(self):
        sentences = ["A.", "B.", "C.", "D.", "E."]
        scenes = [{"scene_number": 1, "duration_seconds": 10.0, "visual": "", "timestamp": ""}]

        result = align_sentences_to_scenes(sentences, scenes)

        assert [r["scene_number"] for r in result] == [1, 2, 3, 4, 5]

    def test_six_sentences_two_scenes_preserves_all_sentences(self):
        """Previously, only 2 cards were created — this must produce 6."""
        sentences = [f"Sentence {i}." for i in range(6)]
        scenes = [
            {"scene_number": 1, "duration_seconds": 12.0, "visual": "V1", "timestamp": ""},
            {"scene_number": 2, "duration_seconds": 18.0, "visual": "V2", "timestamp": ""},
        ]
        result = align_sentences_to_scenes(sentences, scenes)

        assert len(result) == 6
        for i, card in enumerate(result):
            assert card["narration"] == sentences[i], (
                f"Card {i} narration mismatch: expected {sentences[i]!r}, got {card['narration']!r}"
            )

    def test_duration_floor_is_at_least_one_second(self):
        """Even for a huge number of sentences, each card must be ≥ 1 second."""
        sentences = [f"S{i}." for i in range(100)]
        scenes = [{"scene_number": 1, "duration_seconds": 30.0, "visual": "", "timestamp": ""}]

        result = align_sentences_to_scenes(sentences, scenes)

        assert all(r["duration_seconds"] >= 1.0 for r in result)


# ---------------------------------------------------------------------------
# align_sentences_to_scenes — edge cases
# ---------------------------------------------------------------------------


class TestAlignEdgeCases:
    def test_empty_sentences_returns_empty(self):
        scenes = [{"scene_number": 1, "duration_seconds": 5.0, "visual": "", "timestamp": ""}]
        result = align_sentences_to_scenes([], scenes)
        assert result == []

    def test_empty_scenes_uses_placeholder_duration(self):
        sentences = ["Only sentence."]
        result = align_sentences_to_scenes(sentences, [])

        assert len(result) == 1
        assert result[0]["narration"] == "Only sentence."
        assert result[0]["duration_seconds"] == 5.0

    def test_both_empty_returns_empty(self):
        result = align_sentences_to_scenes([], [])
        assert result == []

    def test_single_sentence_single_scene(self):
        sentences = ["Hello world."]
        scenes = [{"scene_number": 1, "duration_seconds": 7.5, "visual": "sky", "timestamp": "00:00"}]

        result = align_sentences_to_scenes(sentences, scenes)

        assert len(result) == 1
        assert result[0]["narration"] == "Hello world."
        assert result[0]["duration_seconds"] == pytest.approx(7.5)
        assert result[0]["visual"] == "sky"

    def test_output_always_has_narration_key(self):
        """Every output card must carry a 'narration' key."""
        sentences = ["A.", "B.", "C."]
        scenes = [
            {"scene_number": 1, "duration_seconds": 5.0, "visual": "", "timestamp": ""},
            {"scene_number": 2, "duration_seconds": 5.0, "visual": "", "timestamp": ""},
        ]
        result = align_sentences_to_scenes(sentences, scenes)
        for card in result:
            assert "narration" in card

    def test_output_always_has_duration_key(self):
        sentences = ["A.", "B.", "C."]
        scenes = [{"scene_number": i + 1, "duration_seconds": 4.0, "visual": "", "timestamp": ""} for i in range(6)]
        result = align_sentences_to_scenes(sentences, scenes)
        for card in result:
            assert "duration_seconds" in card
            assert card["duration_seconds"] > 0

    def test_scenes_without_timestamp_field(self):
        """Scenes may omit the timestamp key — should not raise."""
        sentences = ["Test."]
        scenes = [{"scene_number": 1, "duration_seconds": 3.0, "visual": "V"}]

        result = align_sentences_to_scenes(sentences, scenes)

        assert len(result) == 1
        assert result[0]["timestamp"] == ""

    def test_scenes_without_visual_field(self):
        """Scenes may omit the visual key — should not raise."""
        sentences = ["Test."]
        scenes = [{"scene_number": 1, "duration_seconds": 3.0, "timestamp": ""}]

        result = align_sentences_to_scenes(sentences, scenes)

        assert result[0]["visual"] == ""


# ---------------------------------------------------------------------------
# Sync contract: screen text == spoken audio
# ---------------------------------------------------------------------------


class TestSyncContract:
    """End-to-end invariant: whatever the ratio of sentences to scenes,
    card[i]['narration'] must always equal sentences[i]."""

    @pytest.mark.parametrize(
        "n_sentences,n_scenes",
        [
            (1, 1),
            (1, 5),
            (2, 4),
            (3, 3),
            (4, 2),
            (5, 1),
            (6, 4),
            (10, 3),
        ],
    )
    def test_narration_always_matches_sentence(self, n_sentences: int, n_scenes: int):
        sentences = [f"Sentence number {i + 1}." for i in range(n_sentences)]
        scenes = [
            {
                "scene_number": i + 1,
                "duration_seconds": 5.0,
                "visual": f"Visual {i}",
                "timestamp": "",
            }
            for i in range(n_scenes)
        ]

        result = align_sentences_to_scenes(sentences, scenes)

        assert len(result) == n_sentences, (
            f"Expected {n_sentences} cards for {n_sentences} sentences/{n_scenes} scenes, "
            f"got {len(result)}"
        )
        for i, card in enumerate(result):
            assert card["narration"] == sentences[i], (
                f"Card {i}: expected {sentences[i]!r}, got {card['narration']!r}"
            )