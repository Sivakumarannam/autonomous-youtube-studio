"""Unit tests for app/rag/vector_store.py (Item 5)."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import numpy as np
import pytest

from app.rag.vector_store import Chunk, VectorStore

# Dimension must match EMBEDDING_DIM
_DIM = 384


def _unit_vec(seed: int = 0) -> list[float]:
    """Return a reproducible unit vector of dim _DIM."""
    rng = np.random.default_rng(seed)
    v = rng.standard_normal(_DIM).astype("float32")
    v /= np.linalg.norm(v)
    return v.tolist()


def _make_chunk(topic_id: str = "topic-1", text: str = "sample chunk text") -> Chunk:
    return Chunk(
        chunk_id=str(uuid.uuid4()),
        chunk_text=text,
        source_url="https://example.com",
        topic_id=topic_id,
        document_id=str(uuid.uuid4()),
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def store(tmp_path):
    """A fresh VectorStore backed by a temp directory."""
    s = VectorStore(db_path=str(tmp_path))
    yield s
    s.close()


# ---------------------------------------------------------------------------
# has_chunks_for_topic
# ---------------------------------------------------------------------------

class TestHasChunksForTopic:
    @pytest.mark.asyncio
    async def test_returns_false_when_empty(self, store):
        assert await store.has_chunks_for_topic("nonexistent") is False

    @pytest.mark.asyncio
    async def test_returns_true_after_upsert(self, store):
        chunk = _make_chunk("t1")
        vec = _unit_vec(0)
        await store.upsert_chunks([chunk], [vec])
        assert await store.has_chunks_for_topic("t1") is True

    @pytest.mark.asyncio
    async def test_returns_false_for_different_topic(self, store):
        chunk = _make_chunk("t1")
        await store.upsert_chunks([chunk], [_unit_vec(0)])
        assert await store.has_chunks_for_topic("t2") is False


# ---------------------------------------------------------------------------
# upsert_chunks
# ---------------------------------------------------------------------------

class TestUpsertChunks:
    @pytest.mark.asyncio
    async def test_stores_multiple_chunks(self, store):
        chunks = [_make_chunk("t1", f"text {i}") for i in range(3)]
        vecs = [_unit_vec(i) for i in range(3)]
        await store.upsert_chunks(chunks, vecs)
        assert await store.has_chunks_for_topic("t1") is True

    @pytest.mark.asyncio
    async def test_idempotent_on_duplicate_chunk_ids(self, store):
        chunk = _make_chunk("t1")
        vec = _unit_vec(0)
        await store.upsert_chunks([chunk], [vec])
        await store.upsert_chunks([chunk], [vec])  # second insert: no-op
        # FAISS should only have 1 vector
        assert store._index is not None
        assert store._index.ntotal == 1

    @pytest.mark.asyncio
    async def test_raises_on_length_mismatch(self, store):
        chunks = [_make_chunk()]
        with pytest.raises(ValueError, match="length mismatch"):
            await store.upsert_chunks(chunks, [])

    @pytest.mark.asyncio
    async def test_noop_on_empty_input(self, store):
        await store.upsert_chunks([], [])  # must not raise


# ---------------------------------------------------------------------------
# query
# ---------------------------------------------------------------------------

class TestQuery:
    @pytest.mark.asyncio
    async def test_returns_empty_when_store_empty(self, store):
        with patch("app.rag.vector_store.encode", new_callable=AsyncMock) as mock_enc:
            mock_enc.return_value = [_unit_vec(0)]
            results = await store.query("test query", topic_id="t1", k=3)
        assert results == []

    @pytest.mark.asyncio
    async def test_returns_chunk_for_matching_topic(self, store):
        chunk = _make_chunk("t1", "solar panels generate electricity")
        vec = _unit_vec(7)
        await store.upsert_chunks([chunk], [vec])

        with patch("app.rag.vector_store.encode", new_callable=AsyncMock) as mock_enc:
            mock_enc.return_value = [_unit_vec(7)]  # identical → highest cosine sim
            results = await store.query("solar panels", topic_id="t1", k=3)

        assert len(results) == 1
        assert results[0].chunk_id == chunk.chunk_id
        assert results[0].topic_id == "t1"

    @pytest.mark.asyncio
    async def test_does_not_return_chunks_from_other_topic(self, store):
        chunk_t1 = _make_chunk("t1", "topic one content here is long enough to store")
        chunk_t2 = _make_chunk("t2", "topic two content here is long enough to store")
        await store.upsert_chunks([chunk_t1, chunk_t2], [_unit_vec(0), _unit_vec(1)])

        with patch("app.rag.vector_store.encode", new_callable=AsyncMock) as mock_enc:
            mock_enc.return_value = [_unit_vec(0)]
            results = await store.query("test", topic_id="t2", k=5)

        assert all(r.topic_id == "t2" for r in results)

    @pytest.mark.asyncio
    async def test_respects_k_limit(self, store):
        chunks = [_make_chunk("t1", f"chunk {i} with enough text") for i in range(10)]
        vecs = [_unit_vec(i) for i in range(10)]
        await store.upsert_chunks(chunks, vecs)

        with patch("app.rag.vector_store.encode", new_callable=AsyncMock) as mock_enc:
            mock_enc.return_value = [_unit_vec(0)]
            results = await store.query("test", topic_id="t1", k=3)

        assert len(results) <= 3

    @pytest.mark.asyncio
    async def test_results_sorted_by_score_descending(self, store):
        chunks = [_make_chunk("t1", f"chunk {i}") for i in range(5)]
        vecs = [_unit_vec(i) for i in range(5)]
        await store.upsert_chunks(chunks, vecs)

        with patch("app.rag.vector_store.encode", new_callable=AsyncMock) as mock_enc:
            mock_enc.return_value = [_unit_vec(2)]
            results = await store.query("test", topic_id="t1", k=5)

        scores = [r.score for r in results]
        assert scores == sorted(scores, reverse=True)


# ---------------------------------------------------------------------------
# delete_topic
# ---------------------------------------------------------------------------

class TestDeleteTopic:
    @pytest.mark.asyncio
    async def test_deletes_matching_chunks(self, store):
        chunk = _make_chunk("t1")
        await store.upsert_chunks([chunk], [_unit_vec(0)])
        deleted = await store.delete_topic("t1")
        assert deleted == 1
        assert await store.has_chunks_for_topic("t1") is False

    @pytest.mark.asyncio
    async def test_does_not_delete_other_topics(self, store):
        c1 = _make_chunk("t1")
        c2 = _make_chunk("t2")
        await store.upsert_chunks([c1, c2], [_unit_vec(0), _unit_vec(1)])
        await store.delete_topic("t1")
        assert await store.has_chunks_for_topic("t2") is True

    @pytest.mark.asyncio
    async def test_returns_zero_when_topic_not_found(self, store):
        deleted = await store.delete_topic("nonexistent")
        assert deleted == 0


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

class TestPersistence:
    @pytest.mark.asyncio
    async def test_survives_store_close_and_reopen(self, tmp_path):
        chunk = _make_chunk("t1", "persistent chunk content here")
        vec = _unit_vec(0)

        store1 = VectorStore(db_path=str(tmp_path))
        await store1.upsert_chunks([chunk], [vec])
        store1.close()

        # Re-open with same path
        store2 = VectorStore(db_path=str(tmp_path))
        assert await store2.has_chunks_for_topic("t1") is True
        store2.close()