"""
Embeddings — Item 4 of Phase 4 RAG Research.

Thin async wrapper around sentence-transformers all-MiniLM-L6-v2.

Optional on Oracle free-tier: if sentence-transformers is not installed
(avoids pulling torch/CUDA), encode() raises RuntimeError and callers
(RAG path) catch and continue without vector search.
"""
from __future__ import annotations

import asyncio
import functools

try:
    from sentence_transformers import SentenceTransformer
except ImportError:  # optional — not installed on free-tier CPU image
    SentenceTransformer = None  # type: ignore[misc, assignment]

from app.core.logging import get_logger

logger = get_logger(__name__)

_MODEL_NAME = "all-MiniLM-L6-v2"
_model = None  # type: ignore[var-annotated]

# Public constant so vector_store.py can create the right FAISS index dimension.
EMBEDDING_DIM = 384


def _load_model():
    """Load (or return cached) SentenceTransformer model."""
    global _model
    if SentenceTransformer is None:
        raise RuntimeError(
            "sentence-transformers not installed — RAG embeddings disabled "
            "(expected on Oracle free-tier CPU image)"
        )
    if _model is None:
        logger.info("Loading embedding model", model=_MODEL_NAME)
        _model = SentenceTransformer(_MODEL_NAME)
        logger.info("Embedding model ready", model=_MODEL_NAME, dim=EMBEDDING_DIM)
    return _model


def _encode_sync(texts: list[str]) -> list[list[float]]:
    """Synchronous encode; called from thread pool."""
    model = _load_model()
    # normalize_embeddings=True → L2-normalised → inner-product == cosine sim
    vectors = model.encode(texts, show_progress_bar=False, normalize_embeddings=True)
    return vectors.tolist()


async def encode(texts: list[str]) -> list[list[float]]:
    """Encode a list of texts into L2-normalised embedding vectors (dim=384).

    Returns an empty list if *texts* is empty.
    Runs in a thread-pool executor; never blocks the event loop.
    """
    if not texts:
        return []
    loop = asyncio.get_running_loop()
    vectors: list[list[float]] = await loop.run_in_executor(
        None, functools.partial(_encode_sync, texts)
    )
    return vectors
