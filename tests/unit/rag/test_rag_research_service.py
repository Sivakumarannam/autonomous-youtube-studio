"""Unit tests for app/rag/rag_research_service.py (Item 6)."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.rag.extractor import ExtractedContent
from app.rag.rag_research_service import RagResearchService
from app.rag.search import SearchResult
from app.rag.vector_store import Chunk


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

def _make_search_results(n: int = 2) -> list[SearchResult]:
    return [
        SearchResult(url=f"https://example.com/{i}", title=f"Title {i}", snippet=f"Snippet {i}")
        for i in range(n)
    ]


def _make_extracted(n: int = 2) -> list[ExtractedContent]:
    return [
        ExtractedContent(
            text="Solar panels are photovoltaic devices. " * 20,  # > 50 chars
            title=f"Doc {i}",
            source_url=f"https://example.com/{i}",
        )
        for i in range(n)
    ]


def _make_chunk(topic_id: str = "t1") -> Chunk:
    return Chunk(
        chunk_id=str(uuid.uuid4()),
        chunk_text="Solar panels generate electricity efficiently." * 5,
        source_url="https://example.com",
        topic_id=topic_id,
        document_id=str(uuid.uuid4()),
        score=0.9,
    )


@pytest.fixture
def mock_store():
    store = MagicMock()
    store.has_chunks_for_topic = AsyncMock(return_value=False)
    store.upsert_chunks = AsyncMock()
    store.query = AsyncMock(return_value=[])
    store.delete_topic = AsyncMock(return_value=0)
    return store


@pytest.fixture
def enabled_settings():
    with patch("app.rag.rag_research_service.settings") as s:
        s.rag_research_enabled = True
        s.rag_search_max_results = 5
        s.rag_crawl_timeout_seconds = 10
        s.rag_chunk_size = 500
        s.rag_chunk_overlap = 50
        s.rag_chunks_per_topic = 3
        s.serper_api_key = ""
        s.brave_api_key = ""
        yield s


@pytest.fixture
def disabled_settings():
    with patch("app.rag.rag_research_service.settings") as s:
        s.rag_research_enabled = False
        s.rag_chunk_size = 500
        s.rag_chunk_overlap = 50
        s.rag_chunks_per_topic = 3
        yield s


# ---------------------------------------------------------------------------
# enabled property
# ---------------------------------------------------------------------------

class TestEnabled:
    def test_enabled_when_setting_true(self, mock_store):
        with patch("app.rag.rag_research_service.settings") as s:
            s.rag_research_enabled = True
            s.rag_chunk_size = 500
            s.rag_chunk_overlap = 50
            svc = RagResearchService(store=mock_store)
            assert svc.enabled is True

    def test_disabled_when_setting_false(self, mock_store):
        with patch("app.rag.rag_research_service.settings") as s:
            s.rag_research_enabled = False
            s.rag_chunk_size = 500
            s.rag_chunk_overlap = 50
            svc = RagResearchService(store=mock_store)
            assert svc.enabled is False


# ---------------------------------------------------------------------------
# build_for_topic — disabled
# ---------------------------------------------------------------------------

class TestBuildForTopicDisabled:
    @pytest.mark.asyncio
    async def test_returns_zero_when_disabled(self, mock_store, disabled_settings):
        svc = RagResearchService(store=mock_store)
        result = await svc.build_for_topic("t1", "solar panels")
        assert result == 0
        mock_store.upsert_chunks.assert_not_called()


# ---------------------------------------------------------------------------
# build_for_topic — enabled, happy path
# ---------------------------------------------------------------------------

class TestBuildForTopicEnabled:
    @pytest.mark.asyncio
    async def test_stores_chunks_on_success(self, mock_store, enabled_settings):
        svc = RagResearchService(store=mock_store)

        with (
            patch("app.rag.rag_research_service.search", new_callable=AsyncMock) as mock_search,
            patch("app.rag.rag_research_service.crawl_batch", new_callable=AsyncMock) as mock_crawl,
            patch("app.rag.rag_research_service.extract_batch") as mock_extract,
            patch("app.rag.rag_research_service.encode", new_callable=AsyncMock) as mock_enc,
        ):
            mock_search.return_value = _make_search_results(2)
            mock_crawl.return_value = [("https://example.com/0", "<html>ok</html>")]
            mock_extract.return_value = _make_extracted(1)
            mock_enc.return_value = [[0.1] * 384]

            count = await svc.build_for_topic("t1", "solar panels", niche="tech")

        assert count > 0
        mock_store.upsert_chunks.assert_called_once()

    @pytest.mark.asyncio
    async def test_skips_build_when_chunks_already_exist(self, mock_store, enabled_settings):
        mock_store.has_chunks_for_topic = AsyncMock(return_value=True)
        svc = RagResearchService(store=mock_store)

        with patch("app.rag.rag_research_service.search", new_callable=AsyncMock) as mock_search:
            count = await svc.build_for_topic("t1", "solar panels")

        assert count == 0
        mock_search.assert_not_called()

    @pytest.mark.asyncio
    async def test_force_rebuild_bypasses_existing_check(self, mock_store, enabled_settings):
        mock_store.has_chunks_for_topic = AsyncMock(return_value=True)
        svc = RagResearchService(store=mock_store)

        with (
            patch("app.rag.rag_research_service.search", new_callable=AsyncMock) as mock_search,
            patch("app.rag.rag_research_service.crawl_batch", new_callable=AsyncMock),
            patch("app.rag.rag_research_service.extract_batch", return_value=[]),
        ):
            mock_search.return_value = []
            await svc.build_for_topic("t1", "solar panels", force_rebuild=True)

        mock_search.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_zero_when_search_returns_empty(self, mock_store, enabled_settings):
        svc = RagResearchService(store=mock_store)

        with patch("app.rag.rag_research_service.search", new_callable=AsyncMock) as mock_search:
            mock_search.return_value = []
            result = await svc.build_for_topic("t1", "solar panels")

        assert result == 0
        mock_store.upsert_chunks.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_zero_when_all_crawls_fail(self, mock_store, enabled_settings):
        svc = RagResearchService(store=mock_store)

        with (
            patch("app.rag.rag_research_service.search", new_callable=AsyncMock) as mock_search,
            patch("app.rag.rag_research_service.crawl_batch", new_callable=AsyncMock) as mock_crawl,
        ):
            mock_search.return_value = _make_search_results(2)
            mock_crawl.return_value = [("url", ""), ("url2", "")]  # all empty
            result = await svc.build_for_topic("t1", "solar panels")

        assert result == 0
        mock_store.upsert_chunks.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_zero_when_extraction_yields_nothing_useful(
        self, mock_store, enabled_settings
    ):
        svc = RagResearchService(store=mock_store)

        with (
            patch("app.rag.rag_research_service.search", new_callable=AsyncMock) as mock_search,
            patch("app.rag.rag_research_service.crawl_batch", new_callable=AsyncMock) as mock_crawl,
            patch("app.rag.rag_research_service.extract_batch") as mock_extract,
        ):
            mock_search.return_value = _make_search_results(1)
            mock_crawl.return_value = [("url", "<html>x</html>")]
            mock_extract.return_value = [
                ExtractedContent(text="", title="", source_url="url")
            ]
            result = await svc.build_for_topic("t1", "solar panels")

        assert result == 0

    @pytest.mark.asyncio
    async def test_swallows_exceptions_and_returns_zero(self, mock_store, enabled_settings):
        """Any unexpected exception must NOT propagate — return 0 instead."""
        svc = RagResearchService(store=mock_store)

        with patch(
            "app.rag.rag_research_service.search",
            new_callable=AsyncMock,
            side_effect=RuntimeError("unexpected"),
        ):
            result = await svc.build_for_topic("t1", "solar panels")

        assert result == 0


# ---------------------------------------------------------------------------
# retrieve_context — disabled
# ---------------------------------------------------------------------------

class TestRetrieveContextDisabled:
    @pytest.mark.asyncio
    async def test_returns_none_when_disabled(self, mock_store, disabled_settings):
        svc = RagResearchService(store=mock_store)
        result = await svc.retrieve_context("t1", "solar panels")
        assert result is None
        mock_store.query.assert_not_called()


# ---------------------------------------------------------------------------
# retrieve_context — enabled
# ---------------------------------------------------------------------------

class TestRetrieveContextEnabled:
    @pytest.mark.asyncio
    async def test_returns_none_when_no_chunks(self, mock_store, enabled_settings):
        mock_store.query = AsyncMock(return_value=[])
        svc = RagResearchService(store=mock_store)
        result = await svc.retrieve_context("t1", "solar panels")
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_formatted_context_string(self, mock_store, enabled_settings):
        chunks = [_make_chunk("t1"), _make_chunk("t1")]
        mock_store.query = AsyncMock(return_value=chunks)
        svc = RagResearchService(store=mock_store)

        result = await svc.retrieve_context("t1", "solar panels")

        assert result is not None
        assert "Web Research Context" in result
        assert "[1]" in result
        assert "[2]" in result
        assert "example.com" in result

    @pytest.mark.asyncio
    async def test_returns_none_on_exception(self, mock_store, enabled_settings):
        mock_store.query = AsyncMock(side_effect=RuntimeError("db error"))
        svc = RagResearchService(store=mock_store)
        result = await svc.retrieve_context("t1", "solar panels")
        assert result is None

    @pytest.mark.asyncio
    async def test_passes_k_to_store(self, mock_store, enabled_settings):
        mock_store.query = AsyncMock(return_value=[])
        svc = RagResearchService(store=mock_store)

        await svc.retrieve_context("t1", "solar panels", k=7)

        mock_store.query.assert_called_once_with(
            query_text="solar panels",
            topic_id="t1",
            k=7,
        )