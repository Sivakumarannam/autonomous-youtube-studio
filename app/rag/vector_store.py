"""
Vector Store — Item 5 of Phase 4 RAG Research.

Uses FAISS IndexFlatIP (inner-product on L2-normalised vectors = cosine
similarity) for fast ANN search, backed by SQLite for chunk metadata
(chunk_id, chunk_text, source_url, topic_id, document_id).

Why FAISS + SQLite instead of chromadb:
  chromadb is blocked by the Replit package firewall; FAISS is leaner,
  battle-tested (Meta/Facebook), and gives us full control over persistence.

Persistence:
  {rag_vector_db_path}/vectors.index   ← FAISS binary index
  {rag_vector_db_path}/metadata.db     ← SQLite chunk metadata

Topic isolation:
  Metadata rows carry a topic_id column.  FAISS is searched broadly (top-N
  candidates) and then post-filtered by topic_id in SQLite.  Orphan FAISS
  vectors (from a delete_topic call) are harmless — their metadata is gone
  so they never appear in query results.

Thread safety:
  asyncio.Lock protects all FAISS mutations.  encode() is called outside the
  lock (CPU-bound, takes time) so the lock is held only for index I/O.
"""
from __future__ import annotations

import asyncio
import sqlite3
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import faiss
import numpy as np

from app.core.config import settings
from app.core.logging import get_logger
from app.rag.embeddings import EMBEDDING_DIM, encode

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Per-process singleton
#
# All RAG operations must share ONE VectorStore instance so that the single
# asyncio.Lock properly serialises concurrent writes to the same FAISS index
# and SQLite file.  Creating multiple instances (e.g. one per request) means
# each carries its own lock — they do NOT coordinate, leading to corrupted
# index files and SQLite lock errors under concurrency.
#
# Call get_vector_store() everywhere instead of VectorStore() directly.
# Call close_vector_store() during app shutdown (lifespan) to release the
# SQLite connection cleanly.
# ---------------------------------------------------------------------------

_singleton: "VectorStore | None" = None
_singleton_path: str | None = None


def get_vector_store(db_path: str | None = None) -> "VectorStore":
    """Return (or create) the process-wide VectorStore singleton.

    If *db_path* is supplied on first call it overrides settings; subsequent
    calls ignore *db_path* and return the existing instance.
    """
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
    """FAISS + SQLite local vector store.

    Safe for single-process async use.  Not safe for concurrent processes
    writing to the same db_path simultaneously.
    """

    def __init__(self, db_path: str | None = None) -> None:
        base = Path(db_path or settings.rag_vector_db_path)
        base.mkdir(parents=True, exist_ok=True)
        self._index_path = base / "vectors.index"
        self._meta_path = base / "metadata.db"
        self._lock = asyncio.Lock()
        self._index: faiss.Index | None = None
        self._conn: sqlite3.Connection | None = None

    # ------------------------------------------------------------------
    # Lazy initialisation (sync, must be called under self._lock)
    # ------------------------------------------------------------------

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
        """Persist FAISS index to disk (sync, call under lock)."""
        assert self._index is not None
        faiss.write_index(self._index, str(self._index_path))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def has_chunks_for_topic(self, topic_id: str) -> bool:
        """Return True if any chunks are stored for *topic_id*."""
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
        """Store chunks and their embeddings.

        Silently skips chunks whose chunk_id already exists (idempotent).
        *vectors* must be L2-normalised with dim == EMBEDDING_DIM.
        """
        if not chunks:
            return
        if len(chunks) != len(vectors):
            raise ValueError(
                f"chunks/vectors length mismatch: {len(chunks)} vs {len(vectors)}"
            )

        async with self._lock:
            self._ensure_init()
            assert self._index is not None and self._conn is not None

            # Filter to genuinely new chunks
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
        """Return the top-*k* most relevant chunks for *topic_id*.

        Embeds *query_text*, searches FAISS for candidates, then
        post-filters by topic_id in SQLite so only relevant documents are
        returned.  Returns [] if the store is empty or has no chunks for
        this topic.
        """
        top_k = k if k is not None else settings.rag_chunks_per_topic

        # Quick check under lock before doing expensive embedding
        async with self._lock:
            self._ensure_init()
            assert self._index is not None
            n_total = self._index.ntotal

        if n_total == 0:
            return []

        # Embed outside the lock — CPU-bound work
        vecs = await encode([query_text])
        if not vecs:
            return []
        query_vec = np.array([vecs[0]], dtype="float32")

        async with self._lock:
            assert self._index is not None and self._conn is not None

            # Search enough candidates to survive topic_id post-filter
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
        """Delete all chunk metadata for *topic_id*.  Returns row count deleted.

        Note: corresponding FAISS vectors become orphans (their rownums remain
        in the index but are never returned since their metadata is gone).
        This is acceptable — orphan vectors waste a small amount of memory but
        have zero effect on query correctness.
        """
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
        """Close the SQLite connection.  Safe to call multiple times."""
        if self._conn:
            self._conn.close()
            self._conn = None