"""Unit tests for app/rag/extractor.py (Item 3)."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from app.rag.extractor import ExtractedContent, extract, extract_batch


_GOOD_HTML = """
<html>
  <head><title>Solar Panels Guide</title></head>
  <body>
    <nav>Navigation junk</nav>
    <article>
      <p>Solar panels are photovoltaic devices that convert sunlight into electricity.</p>
      <p>They are made of silicon cells and can last 25-30 years with minimal maintenance.</p>
      <p>A typical residential installation ranges from 5 kW to 10 kW capacity.</p>
    </article>
    <footer>Footer junk</footer>
  </body>
</html>
"""

_MINIMAL_HTML = "<html><body><p>Too short.</p></body></html>"


# ---------------------------------------------------------------------------
# ExtractedContent
# ---------------------------------------------------------------------------

class TestExtractedContent:
    def test_is_empty_true_for_short_text(self):
        ec = ExtractedContent(text="short", title="T", source_url="https://x.com")
        assert ec.is_empty is True

    def test_is_empty_false_for_long_text(self):
        ec = ExtractedContent(text="x" * 100, title="T", source_url="https://x.com")
        assert ec.is_empty is False

    def test_is_empty_true_for_empty_string(self):
        ec = ExtractedContent(text="", title="", source_url="")
        assert ec.is_empty is True


# ---------------------------------------------------------------------------
# extract — trafilatura success path
# ---------------------------------------------------------------------------

class TestExtractTrafilatura:
    def test_uses_trafilatura_result_when_long_enough(self):
        long_text = "Solar panels generate clean electricity from sunlight. " * 5
        with patch("app.rag.extractor.trafilatura.extract", return_value=long_text):
            result = extract(_GOOD_HTML, "https://example.com")

        assert result.text == long_text.strip()
        assert result.source_url == "https://example.com"
        assert result.is_empty is False

    def test_falls_back_to_bs4_when_trafilatura_returns_none(self):
        with patch("app.rag.extractor.trafilatura.extract", return_value=None):
            result = extract(_GOOD_HTML, "https://example.com")

        # bs4 fallback should capture the <p> tags
        assert not result.is_empty
        assert "solar" in result.text.lower() or "photovoltaic" in result.text.lower()

    def test_falls_back_to_bs4_when_trafilatura_raises(self):
        with patch("app.rag.extractor.trafilatura.extract", side_effect=Exception("boom")):
            result = extract(_GOOD_HTML, "https://example.com")

        assert not result.is_empty

    def test_returns_empty_for_empty_html(self):
        result = extract("", "https://example.com")
        assert result.is_empty

    def test_extracts_title(self):
        long_text = "A" * 200
        with patch("app.rag.extractor.trafilatura.extract", return_value=long_text):
            result = extract(_GOOD_HTML, "https://example.com")

        assert result.title == "Solar Panels Guide"

    def test_returns_empty_when_both_methods_fail(self):
        with patch("app.rag.extractor.trafilatura.extract", return_value="short"):
            result = extract(_MINIMAL_HTML, "https://example.com")

        assert result.is_empty


# ---------------------------------------------------------------------------
# extract_batch
# ---------------------------------------------------------------------------

class TestExtractBatch:
    def test_processes_all_items(self):
        long_text = "X" * 200
        with patch("app.rag.extractor.trafilatura.extract", return_value=long_text):
            results = extract_batch([(_GOOD_HTML, "https://a.com"), (_GOOD_HTML, "https://b.com")])

        assert len(results) == 2
        assert all(not r.is_empty for r in results)

    def test_isolates_per_item_failures(self):
        """An exception in extract() for one item does not abort the batch."""
        call_count = [0]

        def fake_extract(html, url):
            call_count[0] += 1
            if call_count[0] == 1:
                raise RuntimeError("boom inside extract")
            return ExtractedContent(text="X" * 200, title="T", source_url=url)

        # Patch the whole extract() function that extract_batch() calls, not trafilatura.
        with patch("app.rag.extractor.extract", side_effect=fake_extract):
            results = extract_batch([(_GOOD_HTML, "https://bad.com"), (_GOOD_HTML, "https://good.com")])

        assert len(results) == 2
        assert results[0].is_empty
        assert not results[1].is_empty

    def test_empty_input_returns_empty(self):
        assert extract_batch([]) == []

    def test_skips_empty_html_gracefully(self):
        results = extract_batch([("", "https://empty.com")])
        assert len(results) == 1
        assert results[0].is_empty