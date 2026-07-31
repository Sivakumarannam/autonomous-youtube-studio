"""Unit tests for app/rag/embeddings.py (Item 4)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

import app.rag.embeddings as emb_module
from app.rag.embeddings import EMBEDDING_DIM, encode


@pytest.fixture(autouse=True)
def reset_model_cache():
    """Reset the module-level model cache between tests."""
    original = emb_module._model
    emb_module._model = None
    yield
    emb_module._model = None


def _make_fake_model(dim: int = EMBEDDING_DIM):
    """Return a mock SentenceTransformer whose encode() returns unit vectors."""
    mock = MagicMock()

    def fake_encode(texts, show_progress_bar=False, normalize_embeddings=True):
        n = len(texts)
        vecs = np.ones((n, dim), dtype="float32")
        norms = np.linalg.norm(vecs, axis=1, keepdims=True)
        return vecs / norms

    mock.encode.side_effect = fake_encode
    return mock


# ---------------------------------------------------------------------------
# encode()
# ---------------------------------------------------------------------------

class TestEncode:
    @pytest.mark.asyncio
    async def test_returns_empty_list_for_empty_input(self):
        result = await encode([])
        assert result == []

    @pytest.mark.asyncio
    async def test_returns_one_vector_per_text(self):
        fake_model = _make_fake_model()
        with patch("app.rag.embeddings.SentenceTransformer", return_value=fake_model):
            result = await encode(["hello", "world"])

        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_vector_has_correct_dimension(self):
        fake_model = _make_fake_model()
        with patch("app.rag.embeddings.SentenceTransformer", return_value=fake_model):
            result = await encode(["test sentence"])

        assert len(result[0]) == EMBEDDING_DIM

    @pytest.mark.asyncio
    async def test_vectors_are_normalised(self):
        """Vectors must have unit L2 norm (inner product == cosine similarity)."""
        fake_model = _make_fake_model()
        with patch("app.rag.embeddings.SentenceTransformer", return_value=fake_model):
            result = await encode(["normalisation test"])

        vec = np.array(result[0])
        norm = np.linalg.norm(vec)
        assert abs(norm - 1.0) < 1e-5

    @pytest.mark.asyncio
    async def test_model_is_loaded_only_once(self):
        fake_model = _make_fake_model()
        with patch("app.rag.embeddings.SentenceTransformer", return_value=fake_model) as mock_cls:
            await encode(["first call"])
            await encode(["second call"])

        # Constructor called exactly once — model is cached
        assert mock_cls.call_count == 1

    @pytest.mark.asyncio
    async def test_returns_list_of_lists(self):
        fake_model = _make_fake_model()
        with patch("app.rag.embeddings.SentenceTransformer", return_value=fake_model):
            result = await encode(["a", "b", "c"])

        assert isinstance(result, list)
        assert all(isinstance(v, list) for v in result)
        assert all(isinstance(x, float) for x in result[0])


# ---------------------------------------------------------------------------
# EMBEDDING_DIM constant
# ---------------------------------------------------------------------------

class TestEmbeddingDim:
    def test_dimension_is_384(self):
        assert EMBEDDING_DIM == 384
