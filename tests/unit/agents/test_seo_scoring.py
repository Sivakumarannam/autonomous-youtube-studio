"""Unit tests for app/agents/seo_agent/scoring.py.

All tests are pure-Python — no database, no async, no LLM.
"""
import json
import pytest

from app.agents.seo_agent.scoring import score_seo_metadata, SeoScoreBreakdown


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _tags_json(tags: list[str]) -> str:
    return json.dumps(tags)


def _hashtags_json(tags: list[str]) -> str:
    return json.dumps(tags)


def _desc_with_hashtags(n: int, extra: str = "") -> str:
    """Return a description ≥ 100 chars with n embedded #hashtags and a CTA."""
    tags = " ".join(f"#tag{i}" for i in range(n))
    base = f"Subscribe to our channel for more! {tags} {extra}"
    if len(base) < 100:
        base += " " * (100 - len(base) + 1)
    return base


# ---------------------------------------------------------------------------
# Title score
# ---------------------------------------------------------------------------

class TestTitleScore:
    """title_score covers length, clickbait, keyword — max 25 pts."""

    def test_optimal_length_no_clickbait_with_keyword(self):
        title = "Python Machine Learning Tutorial for Beginners 2026"  # 51 chars
        # Build tags that contain a keyword present in the title
        tags = _tags_json(["python", "machine learning", "tutorial"])
        result = score_seo_metadata(title, None, tags, None)
        # keyword present → 7 pts; no clickbait → 8 pts; length 51 → 5 pts (45-85)
        assert result.title_score == pytest.approx(5.0 + 8.0 + 7.0)
        assert result.has_keyword_in_title is True
        assert result.has_clickbait is False

    def test_length_in_optimal_range_scores_10(self):
        title = "Best Python Tutorial for Machine Learning 2026 HD"  # 50 chars - adjust
        # Make it 62 chars
        title = "Best Python Tutorial for Complete Machine Learning 2026"  # 55 chars
        title = "Best Python Tutorial for Complete Machine Learning in 2026"  # 58 chars
        title = "The Best Python Tutorial for Machine Learning Beginners 2026"  # 60 chars exactly
        assert len(title) == 60
        tags = _tags_json(["python"])
        result = score_seo_metadata(title, None, tags, None)
        assert result.title_score == pytest.approx(10.0 + 8.0 + 7.0)

    def test_length_outside_range_scores_0(self):
        title = "Hi"  # 2 chars — way below 45
        result = score_seo_metadata(title, None, None, None)
        # length=0, no clickbait=8, no keyword=0
        assert result.title_score == pytest.approx(0.0 + 8.0 + 0.0)

    def test_clickbait_detected_removes_8_pts(self):
        title = "Shocking Python tips that will change your life forever today"  # has 'shocking'
        assert len(title) == 61  # in 60-70 optimal range → 10 pts for length
        tags = _tags_json(["python"])
        result = score_seo_metadata(title, None, tags, None)
        assert result.has_clickbait is True
        # length 60 → 10 pts; clickbait → 0 pts; keyword 'python' in title → 7 pts
        assert result.title_score == pytest.approx(10.0 + 0.0 + 7.0)

    def test_no_keyword_match_gives_0_keyword_pts(self):
        title = "Completely Unrelated Title About Nothing In Particular Here"
        tags = _tags_json(["python", "machine"])
        result = score_seo_metadata(title, None, tags, None)
        # "nothing" and "unrelated" are > 3 chars but not in tags;
        # "particular" not in tags either
        assert result.has_keyword_in_title is False

    def test_empty_title_no_crash(self):
        result = score_seo_metadata(None, None, None, None)
        assert result.title_score == pytest.approx(0.0 + 8.0 + 0.0)
        assert result.title_length == 0


# ---------------------------------------------------------------------------
# Description score
# ---------------------------------------------------------------------------

class TestDescriptionScore:
    """description_score covers CTA presence and minimum length — max 25 pts."""

    def test_cta_present_and_long_enough(self):
        desc = "Subscribe to our channel for more awesome content! " + "x" * 60
        result = score_seo_metadata(None, desc, None, None)
        assert result.has_cta is True
        assert result.description_length >= 100
        assert result.description_score == pytest.approx(25.0)

    def test_cta_present_but_too_short(self):
        desc = "Subscribe!"
        result = score_seo_metadata(None, desc, None, None)
        assert result.has_cta is True
        assert result.description_length < 100
        assert result.description_score == pytest.approx(15.0)

    def test_no_cta_but_long_enough(self):
        desc = "This video covers everything you need to know. " + "x" * 60
        result = score_seo_metadata(None, desc, None, None)
        assert result.has_cta is False
        assert result.description_length >= 100
        assert result.description_score == pytest.approx(10.0)

    def test_no_cta_and_too_short(self):
        result = score_seo_metadata(None, "Too short.", None, None)
        assert result.description_score == pytest.approx(0.0)

    def test_none_description_no_crash(self):
        result = score_seo_metadata(None, None, None, None)
        assert result.description_score == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Hashtag score
# ---------------------------------------------------------------------------

class TestHashtagScore:
    """hashtag_score counts #word tokens in the description — max 25 pts."""

    def test_seven_or_more_hashtags_scores_25(self):
        desc = _desc_with_hashtags(7)
        result = score_seo_metadata(None, desc, None, None)
        assert result.hashtag_count == 7
        assert result.hashtag_score == pytest.approx(25.0)

    def test_ten_hashtags_also_scores_25(self):
        desc = _desc_with_hashtags(10)
        result = score_seo_metadata(None, desc, None, None)
        assert result.hashtag_count == 10
        assert result.hashtag_score == pytest.approx(25.0)

    def test_four_to_six_hashtags_scores_15(self):
        for n in (4, 5, 6):
            desc = _desc_with_hashtags(n)
            result = score_seo_metadata(None, desc, None, None)
            assert result.hashtag_count == n
            assert result.hashtag_score == pytest.approx(15.0), f"n={n}"

    def test_one_to_three_hashtags_scores_8(self):
        for n in (1, 2, 3):
            desc = _desc_with_hashtags(n)
            result = score_seo_metadata(None, desc, None, None)
            assert result.hashtag_count == n
            assert result.hashtag_score == pytest.approx(8.0), f"n={n}"

    def test_zero_hashtags_scores_0(self):
        desc = "A description with no hashtags at all. " + "x" * 70
        result = score_seo_metadata(None, desc, None, None)
        assert result.hashtag_count == 0
        assert result.hashtag_score == pytest.approx(0.0)

    def test_hashtags_not_embedded_in_description_are_ignored(self):
        # hashtags_json field does not contribute to hashtag_count;
        # only inline #tokens in the description do.
        desc = "No inline hashtags here at all. " + "x" * 70
        hashtags = _hashtags_json(["#python", "#ml", "#ai", "#coding", "#dev", "#tech", "#data"])
        result = score_seo_metadata(None, desc, None, hashtags)
        assert result.hashtag_count == 0
        assert result.hashtag_score == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Tags score
# ---------------------------------------------------------------------------

class TestTagsScore:
    """tags_score counts items in seo_tags JSON list — max 25 pts."""

    def test_twenty_tags_scores_25(self):
        tags = _tags_json([f"tag{i}" for i in range(20)])
        result = score_seo_metadata(None, None, tags, None)
        assert result.tag_count == 20
        assert result.tags_score == pytest.approx(25.0)

    def test_twenty_eight_tags_scores_25(self):
        tags = _tags_json([f"tag{i}" for i in range(28)])
        result = score_seo_metadata(None, None, tags, None)
        assert result.tag_count == 28
        assert result.tags_score == pytest.approx(25.0)

    def test_fifteen_to_nineteen_tags_scores_15(self):
        for n in (15, 17, 19):
            tags = _tags_json([f"tag{i}" for i in range(n)])
            result = score_seo_metadata(None, None, tags, None)
            assert result.tags_score == pytest.approx(15.0), f"n={n}"

    def test_twenty_nine_to_thirty_five_tags_scores_15(self):
        for n in (29, 32, 35):
            tags = _tags_json([f"tag{i}" for i in range(n)])
            result = score_seo_metadata(None, None, tags, None)
            assert result.tags_score == pytest.approx(15.0), f"n={n}"

    def test_fewer_than_15_tags_scores_0(self):
        tags = _tags_json([f"tag{i}" for i in range(10)])
        result = score_seo_metadata(None, None, tags, None)
        assert result.tags_score == pytest.approx(0.0)

    def test_more_than_35_tags_scores_0(self):
        tags = _tags_json([f"tag{i}" for i in range(36)])
        result = score_seo_metadata(None, None, tags, None)
        assert result.tags_score == pytest.approx(0.0)

    def test_malformed_json_gives_0(self):
        result = score_seo_metadata(None, None, "not-json", None)
        assert result.tag_count == 0
        assert result.tags_score == pytest.approx(0.0)

    def test_empty_json_list_gives_0(self):
        result = score_seo_metadata(None, None, "[]", None)
        assert result.tag_count == 0
        assert result.tags_score == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Total / gate threshold
# ---------------------------------------------------------------------------

class TestTotalScore:
    """Integration: full-metadata pass and obvious fail."""

    def test_perfect_metadata_scores_100(self):
        title = "The Best Python Machine Learning Tutorial for Beginners"  # 55 chars → 5 pts length
        # Make it exactly 65 chars
        title = "The Best Python Machine Learning Tutorial for Beginners 2026"  # 60 chars
        assert len(title) == 60
        desc = (
            "Subscribe to our channel for more awesome content! "
            "#python #machinelearning #ai #tutorial #coding #data #science "
            "Watch this video and let us know your thoughts in the comments below!"
        )
        tags = _tags_json([f"tag{i}" for i in range(24)])  # 24 → 25 pts
        hashtags = _hashtags_json(["python", "machine learning"])

        result = score_seo_metadata(title, desc, tags, hashtags)

        assert result.tag_count == 24
        assert result.hashtag_count >= 7
        assert result.has_cta is True
        assert result.description_length >= 100
        assert result.has_keyword_in_title is True
        assert not result.has_clickbait
        # Expect max on each dimension
        assert result.title_score == pytest.approx(10.0 + 8.0 + 7.0)
        assert result.description_score == pytest.approx(25.0)
        assert result.hashtag_score == pytest.approx(25.0)
        assert result.tags_score == pytest.approx(25.0)
        assert result.total == pytest.approx(100.0)

    def test_all_none_inputs_scores_8(self):
        # Only the no-clickbait title bonus (8 pts) is possible with empty inputs.
        result = score_seo_metadata(None, None, None, None)
        assert result.total == pytest.approx(8.0)

    def test_score_passes_default_threshold_of_60(self):
        # Construct metadata that should comfortably clear seo_min_score=60.
        title = "The Best Python Machine Learning Tutorial for Beginners 2026"
        desc = (
            "Subscribe now! #python #ml #ai #tutorial #coding #data #science "
            + "x" * 60
        )
        tags = _tags_json([f"tag{i}" for i in range(22)])
        hashtags = _hashtags_json(["python"])
        result = score_seo_metadata(title, desc, tags, hashtags)
        assert result.total >= 60.0

    def test_score_fails_threshold_when_metadata_empty(self):
        result = score_seo_metadata("Hi", "short", "[]", "[]")
        # title: 0 (length) + 8 (no clickbait) + 0 (keyword) = 8
        # description: 0 (no CTA) + 0 (too short) = 0
        # hashtags: 0 (none inline) = 0
        # tags: 0 (0 tags) = 0
        # total = 8 — well below 60
        assert result.total < 60.0
