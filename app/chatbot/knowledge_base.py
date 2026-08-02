"""Knowledge Base — ingest and delete documents for the Studio Assistant chatbot.

Documents are chunked, embedded, and stored in the shared FAISS vector store
under the reserved topic_id namespaces:
  studio_knowledge   — project docs, FAQs, how-to guides
  studio_resolved_qa — past resolved escalations (grown over time)
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.logging import get_logger
from app.rag.vector_store import get_vector_store, Chunk
from app.rag.embeddings import encode
from app.database.models.chat import KnowledgeDoc

logger = get_logger(__name__)

TOPIC_KNOWLEDGE = "studio_knowledge"
TOPIC_RESOLVED_QA = "studio_resolved_qa"

# Characters per chunk (overlap handled by sliding window)
_CHUNK_SIZE = 800
_CHUNK_OVERLAP = 100


def _split_text(text: str) -> list[str]:
    """Split *text* into overlapping chunks of ~_CHUNK_SIZE characters."""
    if not text.strip():
        return []
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = start + _CHUNK_SIZE
        chunks.append(text[start:end].strip())
        start += _CHUNK_SIZE - _CHUNK_OVERLAP
    return [c for c in chunks if c]


async def ingest_document(
    session: AsyncSession,
    title: str,
    text: str,
    topic_id: str = TOPIC_KNOWLEDGE,
    source_type: str = "manual",
    doc_id: Optional[str] = None,
) -> KnowledgeDoc:
    """Chunk, embed and store *text* into the vector store.

    Returns the persisted KnowledgeDoc record.
    """
    doc_uuid = doc_id or str(uuid.uuid4())
    chunks_text = _split_text(text)
    if not chunks_text:
        raise ValueError("Document is empty after chunking")

    # Build Chunk objects
    chunks = [
        Chunk(
            chunk_id=f"{doc_uuid}_{i}",
            chunk_text=ct,
            source_url=f"kb://{topic_id}/{doc_uuid}",
            topic_id=topic_id,
            document_id=doc_uuid,
        )
        for i, ct in enumerate(chunks_text)
    ]

    # Embed all chunks
    vectors = await encode(chunks_text)

    # Store in FAISS + SQLite metadata
    store = get_vector_store()
    await store.upsert_chunks(chunks, vectors)

    # Persist metadata record
    doc = KnowledgeDoc(
        id=uuid.UUID(doc_uuid),
        title=title,
        source_type=source_type,
        topic_id=topic_id,
        chunk_count=len(chunks),
        active=True,
        ingested_at=datetime.now(timezone.utc),
    )
    session.add(doc)
    await session.commit()
    await session.refresh(doc)

    logger.info(
        "Knowledge doc ingested",
        title=title,
        chunks=len(chunks),
        topic_id=topic_id,
        doc_id=doc_uuid,
    )
    return doc


async def delete_document(session: AsyncSession, doc_id: uuid.UUID) -> bool:
    """Remove a document from the knowledge base (vector store + DB record).

    Returns True if the document was found and deleted.
    """
    result = await session.execute(
        select(KnowledgeDoc).where(KnowledgeDoc.id == doc_id)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        return False

    # Remove chunks from vector store metadata (orphan FAISS vectors are harmless)
    store = get_vector_store()
    doc_uuid_str = str(doc_id)
    async with store._lock:
        store._ensure_init()
        assert store._conn is not None
        store._conn.execute(
            "DELETE FROM chunks WHERE document_id = ?", (doc_uuid_str,)
        )
        store._conn.commit()

    await session.delete(doc)
    await session.commit()

    logger.info("Knowledge doc deleted", doc_id=str(doc_id), title=doc.title)
    return True


async def list_documents(
    session: AsyncSession,
    topic_id: Optional[str] = None,
) -> list[KnowledgeDoc]:
    """Return all KnowledgeDocs, optionally filtered by topic_id."""
    q = select(KnowledgeDoc).order_by(KnowledgeDoc.ingested_at.desc())
    if topic_id:
        q = q.where(KnowledgeDoc.topic_id == topic_id)
    result = await session.execute(q)
    return list(result.scalars().all())


async def has_any_knowledge_docs(session: AsyncSession) -> bool:
    """Return True if the knowledge base has been seeded."""
    result = await session.execute(
        select(KnowledgeDoc).where(KnowledgeDoc.topic_id == TOPIC_KNOWLEDGE).limit(1)
    )
    return result.scalar_one_or_none() is not None
