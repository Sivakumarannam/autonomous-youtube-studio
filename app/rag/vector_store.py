"""
Vector Store — Item 5 of Phase 4 RAG Research.

Uses FAISS IndexFlatIP (inner-product on L2-normalised vectors = cosine
similarity) for fast ANN search, backed by SQLite for chunk metadata
(chunk_id, chunk_text, source_url, topic_id, document_id).

FAISS is optional: if not installed (Oracle free-tier CPU image without
torch/CUDA stack), get_vector_store() raises and callers skip RAG.
"""
from __future__ import annotations

import asyncio
import sqlite3
import uuid
from dataclasses import dataclass, field
from pathlib import Path

try:
    import faiss
except ImportError:  # optional on free-tier (avoids torch/CUDA stack)
    faiss = None  # type: ignore[assignment]

import numpy as np

from app.core.config import settings
from app.core.logging import get_logger
from app.rag.embeddings import EMBEDDING_DIM, encode

logger = get_logger(__name__)

_singleton: "VectorStore | None" = None
_singleton_path: str | None = None


def get_vector_store(db_path: str | None = None) -> "VectorStore":
    """Return (or create) the process-wide VectorStore singleton."""
    if faiss is None:
        raise RuntimeError(
            "faiss not installed — RAG vector store disabled "
            "(expected on Oracle free-tier CPU image)"
        )
    global _singleton, _singleton_path
    if _singleton is None:
        _singleton = VectorStore(db_path=db_path)
        _singleton_path = db_path
        logger.info("VectorStore singleton created", path=db_path or settings.rag_vector_db_path)
    return _singleton


def close_vector_store() -> None:
    """Close the singleton and release file handles.  Call at app shutdown."""
    global _singleton
    if _singleton is not None:
        _singleton.close()
        _singleton = None
        logger.info("VectorStore singleton closed")


@dataclass
class Chunk:
    chunk_id: str
    chunk_text: str
    source_url: str
    topic_id: str
    document_id: str
    score: float = field(default=0.0, compare=False)


class VectorStore:
    """FAISS + SQLite local vector store."""

    def __init__(self, db_path: str | None = None) -> None:
        base = Path(db_path or settings.rag_vector_db_path)
        base.mkdir(parents=True, exist_ok=True)
        self._index_path = base / "vectors.index"
        self._meta_path = base / "metadata.db"
        self._lock = asyncio.Lock()
        self._index = None
        self._conn: sqlite3.Connection | None = None

    def _ensure_init(self) -> None:
        if self._index is not None:
            return

        if self._index_path.exists():
            self._index = faiss.read_index(str(self._index_path))
            logger.info(
                "FAISS index loaded from disk",
                path=str(self._index_path),
                ntotal=self._index.ntotal,
            )
        else:
            self._index = faiss.IndexFlatIP(EMBEDDING_DIM)
            logger.info("FAISS index created (new)", dim=EMBEDDING_DIM)

        self._conn = sqlite3.connect(str(self._meta_path), check_same_thread=False)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS chunks (
                rownum      INTEGER PRIMARY KEY,
                chunk_id    TEXT    NOT NULL UNIQUE,
                chunk_text  TEXT    NOT NULL,
                source_url  TEXT    NOT NULL,
                topic_id    TEXT    NOT NULL,
                document_id TEXT    NOT NULL
            )
        """)
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_topic ON chunks(topic_id)"
        )
        self._conn.commit()

    def _save_index(self) -> None:
        assert self._index is not None
        faiss.write_index(self._index, str(self._index_path))

    async def has_chunks_for_topic(self, topic_id: str) -> bool:
        async with self._lock:
            self._ensure_init()
            assert self._conn is not None
            row = self._conn.execute(
                "SELECT 1 FROM chunks WHERE topic_id = ? LIMIT 1", (topic_id,)
            ).fetchone()
            return row is not None

    async def upsert_chunks(
        self, chunks: list[Chunk], vectors: list[list[float]]
    ) -> None:
        if not chunks:
            return
        if len(chunks) != len(vectors):
            raise ValueError(
                f"chunks/vectors length mismatch: {len(chunks)} vs {len(vectors)}"
            )

        async with self._lock:
            self._ensure_init()
            assert self._index is not None and self._conn is not None

            new_chunks: list[Chunk] = []
            new_vecs: list[list[float]] = []
            for chunk, vec in zip(chunks, vectors):
                exists = self._conn.execute(
                    "SELECT 1 FROM chunks WHERE chunk_id = ?", (chunk.chunk_id,)
                ).fetchone()
                if not exists:
                    new_chunks.append(chunk)
                    new_vecs.append(vec)

            if not new_chunks:
                logger.debug("upsert_chunks: all chunks already stored, skipping")
                return

            start_rownum = self._index.ntotal
            vecs_np = np.array(new_vecs, dtype="float32")
            self._index.add(vecs_np)

            rows = [
                (
                    start_rownum + i,
                    c.chunk_id,
                    c.chunk_text,
                    c.source_url,
                    c.topic_id,
                    c.document_id,
                )
                for i, c in enumerate(new_chunks)
            ]
            self._conn.executemany(
                """INSERT OR IGNORE INTO chunks
                   (rownum, chunk_id, chunk_text, source_url, topic_id, document_id)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                rows,
            )
            self._conn.commit()
            self._save_index()

            logger.info(
                "VectorStore upserted chunks",
                new=len(new_chunks),
                total=self._index.ntotal,
            )

    async def query(
        self,
        query_text: str,
        topic_id: str,
        k: int | None = None,
    ) -> list[Chunk]:
        top_k = k if k is not None else settings.rag_chunks_per_topic

        async with self._lock:
            self._ensure_init()
            assert self._index is not None
            n_total = self._index.ntotal

        if n_total == 0:
            return []

        vecs = await encode([query_text])
        if not vecs:
            return []
        query_vec = np.array([vecs[0]], dtype="float32")

        async with self._lock:
            assert self._index is not None and self._conn is not None

            n_search = min(n_total, max(top_k * 20, 50))
            distances, indices = self._index.search(query_vec, n_search)

            found_rownums = [int(i) for i in indices[0] if i >= 0]
            if not found_rownums:
                return []

            placeholders = ",".join("?" * len(found_rownums))
            rows = self._conn.execute(
                f"SELECT rownum, chunk_id, chunk_text, source_url, topic_id, document_id "
                f"FROM chunks WHERE rownum IN ({placeholders}) AND topic_id = ?",
                (*found_rownums, topic_id),
            ).fetchall()

        if not rows:
            return []

        score_map: dict[int, float] = {
            int(idx): float(dist)
            for idx, dist in zip(indices[0], distances[0])
        }
        results: list[Chunk] = [
            Chunk(
                chunk_id=row[1],
                chunk_text=row[2],
                source_url=row[3],
                topic_id=row[4],
                document_id=row[5],
                score=score_map.get(row[0], 0.0),
            )
            for row in rows
        ]
        results.sort(key=lambda c: c.score, reverse=True)
        return results[:top_k]

    async def delete_topic(self, topic_id: str) -> int:
        async with self._lock:
            self._ensure_init()
            assert self._conn is not None
            cur = self._conn.execute(
                "DELETE FROM chunks WHERE topic_id = ?", (topic_id,)
            )
            self._conn.commit()
            logger.info(
                "VectorStore deleted topic chunks",
                topic_id=topic_id,
                deleted=cur.rowcount,
            )
            return cur.rowcount

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None
