"""Unit tests for app/rag/search.py (Item 1)."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.rag.search import (
    SearchResult,
    _parse_ddg_html,
    _search_brave,
    _search_duckduckgo,
    _search_serper,
    search,
)

# ---------------------------------------------------------------------------
# HTML fixture that matches DuckDuckGo's result structure
# ---------------------------------------------------------------------------
_SAMPLE_DDG_HTML = """
<html><body>
  <div class="result results_links_deep web-result">
    <h2 class="result__title">
      <a class="result__a" href="https://example.com/solar-panels">
        Best Solar Panels 2024
      </a>
    </h2>
    <a class="result__snippet">Solar panels can reduce electricity bills by up to 90%.</a>
  </div>
  <div class="result results_links_deep web-result">
    <h2 class="result__title">
      <a class="result__a" href="https://example.org/installation">
        How to Install Solar Panels
      </a>
    </h2>
    <a class="result__snippet">Step-by-step guide for residential solar installation.</a>
  </div>
  <div class="result results_links_deep web-result">
    <h2 class="result__title">
      <a class="result__a" href="//duckduckgo.com/y.js?something">DDG internal</a>
    </h2>
  </div>
</body></html>
"""


# ---------------------------------------------------------------------------
# _parse_ddg_html
# ---------------------------------------------------------------------------

class TestParseDdgHtml:
    def test_parses_valid_results(self):
        results = _parse_ddg_html(_SAMPLE_DDG_HTML, max_results=10)
        assert len(results) == 2
        assert results[0].url == "https://example.com/solar-panels"
        assert "Solar" in results[0].title
        assert "90%" in results[0].snippet

    def test_skips_ddg_internal_links(self):
        results = _parse_ddg_html(_SAMPLE_DDG_HTML, max_results=10)
        assert all("duckduckgo" not in r.url for r in results)

    def test_respects_max_results(self):
        results = _parse_ddg_html(_SAMPLE_DDG_HTML, max_results=1)
        assert len(results) == 1

    def test_empty_html_returns_empty_list(self):
        assert _parse_ddg_html("", max_results=5) == []

    def test_no_matching_divs_returns_empty(self):
        assert _parse_ddg_html("<html><body><p>Nothing here</p></body></html>", max_results=5) == []

    def test_result_is_frozen_dataclass(self):
        results = _parse_ddg_html(_SAMPLE_DDG_HTML, max_results=10)
        r = results[0]
        with pytest.raises((AttributeError, TypeError)):
            r.url = "mutated"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# _search_duckduckgo
# ---------------------------------------------------------------------------

class TestSearchDuckDuckGo:
    @pytest.mark.asyncio
    async def test_returns_parsed_results_on_success(self):
        mock_resp = MagicMock()
        mock_resp.text = _SAMPLE_DDG_HTML
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_resp)

        with patch("app.rag.search.httpx.AsyncClient", return_value=mock_client):
            results = await _search_duckduckgo("solar panels", max_results=5)

        assert len(results) == 2
        assert isinstance(results[0], SearchResult)

    @pytest.mark.asyncio
    async def test_returns_empty_list_on_http_error(self):
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(side_effect=Exception("network error"))

        with patch("app.rag.search.httpx.AsyncClient", return_value=mock_client):
            results = await _search_duckduckgo("solar panels", max_results=5)

        assert results == []


# ---------------------------------------------------------------------------
# _search_serper
# ---------------------------------------------------------------------------

class TestSearchSerper:
    @pytest.mark.asyncio
    async def test_parses_organic_results(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "organic": [
                {"link": "https://a.com", "title": "Result A", "snippet": "Snip A"},
                {"link": "https://b.com", "title": "Result B", "snippet": "Snip B"},
            ]
        }
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_resp)

        with patch("app.rag.search.httpx.AsyncClient", return_value=mock_client):
            results = await _search_serper("solar panels", max_results=5)

        assert len(results) == 2
        assert results[0].url == "https://a.com"

    @pytest.mark.asyncio
    async def test_returns_empty_on_error(self):
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(side_effect=Exception("api error"))

        with patch("app.rag.search.httpx.AsyncClient", return_value=mock_client):
            results = await _search_serper("solar panels", max_results=5)

        assert results == []


# ---------------------------------------------------------------------------
# _search_brave
# ---------------------------------------------------------------------------

class TestSearchBrave:
    @pytest.mark.asyncio
    async def test_parses_web_results(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "web": {
                "results": [
                    {"url": "https://c.com", "title": "C", "description": "Desc C"},
                ]
            }
        }
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_resp)

        with patch("app.rag.search.httpx.AsyncClient", return_value=mock_client):
            results = await _search_brave("solar panels", max_results=5)

        assert len(results) == 1
        assert results[0].url == "https://c.com"

    @pytest.mark.asyncio
    async def test_returns_empty_on_error(self):
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(side_effect=Exception("timeout"))

        with patch("app.rag.search.httpx.AsyncClient", return_value=mock_client):
            results = await _search_brave("solar panels", max_results=5)

        assert results == []


# ---------------------------------------------------------------------------
# search() routing
# ---------------------------------------------------------------------------

class TestSearchRouting:
    @pytest.mark.asyncio
    async def test_uses_ddg_when_no_keys_set(self):
        with (
            patch("app.rag.search.settings") as mock_settings,
            patch("app.rag.search._search_duckduckgo", new_callable=AsyncMock) as mock_ddg,
        ):
            mock_settings.serper_api_key = ""
            mock_settings.brave_api_key = ""
            mock_settings.rag_search_max_results = 5
            mock_ddg.return_value = []

            await search("test query")
            mock_ddg.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_uses_serper_when_key_set(self):
        with (
            patch("app.rag.search.settings") as mock_settings,
            patch("app.rag.search._search_serper", new_callable=AsyncMock) as mock_serper,
        ):
            mock_settings.serper_api_key = "sk-serper"
            mock_settings.brave_api_key = ""
            mock_settings.rag_search_max_results = 5
            mock_serper.return_value = []

            await search("test query")
            mock_serper.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_uses_brave_when_only_brave_key_set(self):
        with (
            patch("app.rag.search.settings") as mock_settings,
            patch("app.rag.search._search_brave", new_callable=AsyncMock) as mock_brave,
        ):
            mock_settings.serper_api_key = ""
            mock_settings.brave_api_key = "brave-key"
            mock_settings.rag_search_max_results = 5
            mock_brave.return_value = []

            await search("test query")
            mock_brave.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_respects_max_results_override(self):
        with (
            patch("app.rag.search.settings") as mock_settings,
            patch("app.rag.search._search_duckduckgo", new_callable=AsyncMock) as mock_ddg,
        ):
            mock_settings.serper_api_key = ""
            mock_settings.brave_api_key = ""
            mock_settings.rag_search_max_results = 5
            mock_ddg.return_value = []

            await search("test query", max_results=3)
            mock_ddg.assert_awaited_once_with("test query", 3)
