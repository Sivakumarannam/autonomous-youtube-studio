"""Unit tests for app/rag/crawler.py (Item 2)."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

import app.rag.crawler as crawler_module
from app.rag.crawler import crawl, crawl_batch


@pytest.fixture(autouse=True)
def clear_robots_cache():
    """Isolate tests from each other via the module-level cache."""
    crawler_module._ROBOTS_CACHE.clear()
    yield
    crawler_module._ROBOTS_CACHE.clear()


# ---------------------------------------------------------------------------
# _is_allowed
# ---------------------------------------------------------------------------

class TestIsAllowed:
    @pytest.mark.asyncio
    async def test_allows_when_robots_permits(self):
        mock_rp = MagicMock()
        mock_rp.can_fetch.return_value = True

        with patch("app.rag.crawler._get_robots", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_rp
            from app.rag.crawler import _is_allowed
            result = await _is_allowed("https://example.com/page")

        assert result is True

    @pytest.mark.asyncio
    async def test_blocks_when_robots_disallows(self):
        mock_rp = MagicMock()
        mock_rp.can_fetch.return_value = False

        with patch("app.rag.crawler._get_robots", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_rp
            from app.rag.crawler import _is_allowed
            result = await _is_allowed("https://example.com/secret")

        assert result is False


# ---------------------------------------------------------------------------
# crawl — success path
# ---------------------------------------------------------------------------

class TestCrawlSuccess:
    @pytest.mark.asyncio
    async def test_returns_html_on_success(self):
        mock_rp = MagicMock()
        mock_rp.can_fetch.return_value = True

        mock_resp = MagicMock()
        mock_resp.text = "<html><body>Hello</body></html>"
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_resp)

        with (
            patch("app.rag.crawler._get_robots", new_callable=AsyncMock, return_value=mock_rp),
            patch("app.rag.crawler.httpx.AsyncClient", return_value=mock_client),
        ):
            result = await crawl("https://example.com/page")

        assert result == "<html><body>Hello</body></html>"

    @pytest.mark.asyncio
    async def test_returns_empty_string_when_robots_disallows(self):
        mock_rp = MagicMock()
        mock_rp.can_fetch.return_value = False

        with patch("app.rag.crawler._get_robots", new_callable=AsyncMock, return_value=mock_rp):
            result = await crawl("https://example.com/disallowed")

        assert result == ""

    @pytest.mark.asyncio
    async def test_returns_empty_string_for_empty_url(self):
        result = await crawl("")
        assert result == ""


# ---------------------------------------------------------------------------
# crawl — failure & retry paths
# ---------------------------------------------------------------------------

class TestCrawlFailures:
    @pytest.mark.asyncio
    async def test_returns_empty_on_non_retryable_error(self):
        mock_rp = MagicMock()
        mock_rp.can_fetch.return_value = True

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        # 404 is non-retryable
        mock_client.get = AsyncMock(
            side_effect=httpx.HTTPStatusError(
                "404", request=MagicMock(), response=MagicMock(status_code=404)
            )
        )

        with (
            patch("app.rag.crawler._get_robots", new_callable=AsyncMock, return_value=mock_rp),
            patch("app.rag.crawler.httpx.AsyncClient", return_value=mock_client),
            patch("app.rag.crawler.asyncio.sleep", new_callable=AsyncMock),
        ):
            result = await crawl("https://example.com/notfound", max_retries=2)

        assert result == ""

    @pytest.mark.asyncio
    async def test_retries_on_timeout_then_succeeds(self):
        """First attempt: timeout (retryable).  Second attempt: success."""
        mock_rp = MagicMock()
        mock_rp.can_fetch.return_value = True

        good_resp = MagicMock()
        good_resp.text = "<html>ok</html>"
        good_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(
            side_effect=[httpx.TimeoutException("timeout"), good_resp]
        )

        with (
            patch("app.rag.crawler._get_robots", new_callable=AsyncMock, return_value=mock_rp),
            patch("app.rag.crawler.httpx.AsyncClient", return_value=mock_client),
            patch("app.rag.crawler.asyncio.sleep", new_callable=AsyncMock),
        ):
            result = await crawl("https://example.com/page", max_retries=2)

        assert result == "<html>ok</html>"

    @pytest.mark.asyncio
    async def test_exhausts_retries_and_returns_empty(self):
        mock_rp = MagicMock()
        mock_rp.can_fetch.return_value = True

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(side_effect=httpx.TimeoutException("timeout"))

        with (
            patch("app.rag.crawler._get_robots", new_callable=AsyncMock, return_value=mock_rp),
            patch("app.rag.crawler.httpx.AsyncClient", return_value=mock_client),
            patch("app.rag.crawler.asyncio.sleep", new_callable=AsyncMock),
        ):
            result = await crawl("https://example.com/page", max_retries=2)

        assert result == ""


# ---------------------------------------------------------------------------
# crawl_batch
# ---------------------------------------------------------------------------

class TestCrawlBatch:
    @pytest.mark.asyncio
    async def test_returns_url_html_pairs(self):
        async def fake_crawl(url: str, **kwargs) -> str:
            return f"<html>{url}</html>"

        with patch("app.rag.crawler.crawl", side_effect=fake_crawl):
            results = await crawl_batch(["https://a.com", "https://b.com"])

        assert results == [
            ("https://a.com", "<html>https://a.com</html>"),
            ("https://b.com", "<html>https://b.com</html>"),
        ]

    @pytest.mark.asyncio
    async def test_isolates_per_url_failures(self):
        async def fake_crawl(url: str, **kwargs) -> str:
            if "bad" in url:
                return ""
            return "<html>ok</html>"

        with patch("app.rag.crawler.crawl", side_effect=fake_crawl):
            results = await crawl_batch(["https://good.com", "https://bad.com"])

        assert results[0] == ("https://good.com", "<html>ok</html>")
        assert results[1] == ("https://bad.com", "")

    @pytest.mark.asyncio
    async def test_empty_input_returns_empty(self):
        results = await crawl_batch([])
        assert results == []