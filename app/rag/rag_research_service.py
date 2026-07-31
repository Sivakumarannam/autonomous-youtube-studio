"""
RAG Research Service — Item 6 of Phase 4 RAG Research.

Orchestrates the full pipeline:
  Search → Crawl → Extract → Chunk → Embed → Store → Retrieve

Designed to be:
  - Optional: does nothing when settings.rag_research_enabled is False
  - Idempotent: skips the build if chunks already exist for a topic
  - Fail-safe: any exception is caught, logged as a warning, and returns
    None/0 — the pipeline always continues without RAG context

Inject context into script prompts by passing the returned string as
rag_context=... to ShortScriptAgent.run() or LongScriptAgent.run().
"""
from __future__ import annotations

import uuid

from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.core.config import settings
from app.core.logging import get_logger
from app.rag.crawler import crawl_batch
from app.rag.embeddings import encode
from app.rag.extractor import ExtractedContent, extract_batch
from app.rag.search import SearchResult, search
from app.rag.vector_store import Chunk, VectorStore, get_vector_store

logger = get_logger(__name__)


class RagResearchService:
    """Orchestrates RAG research for a topic.

    Typical usage in a script agent service:

        svc = RagResearchService()
        await svc.build_for_topic(topic_id=str(topic.id), query=topic.title)
        context = await svc.retrieve_context(topic_id=str(topic.id), query=topic.title)
        script = await agent.run(..., rag_context=context)
    """

    def __init__(self, store: VectorStore | None = None) -> None:
        # Use the process-wide singleton so all concurrent requests share one
        # asyncio.Lock and therefore one consistent FAISS index + SQLite file.
        # Tests may pass an explicit store to inject a mock/temp instance.
        self._store = store if store is not None else get_vector_store()
        self._splitter = RecursiveCharacterTextSplitter(
            chunk_size=settings.rag_chunk_size,
            chunk_overlap=settings.rag_chunk_overlap,
            length_function=len,
        )

    @property
    def enabled(self) -> bool:
        return settings.rag_research_enabled

    # ------------------------------------------------------------------
    # Build pipeline: Search → Crawl → Extract → Chunk → Embed → Store
    # ------------------------------------------------------------------

    async def build_for_topic(
        self,
        topic_id: str,
        query: str,
        niche: str = "general",
        force_rebuild: bool = False,
    ) -> int:
        """Run the full RAG build pipeline for *topic_id*.

        Returns the number of chunks stored (0 if disabled, already built,
        or any step fails).  Never raises.

        Args:
            topic_id: Unique identifier for the topic (used as partition key
                      in the vector store).
            query: The search query, typically the topic title.
            niche: Channel niche appended to the query to improve relevance.
            force_rebuild: If True, rebuilds even when chunks already exist.
        """
        if not self.enabled:
            return 0

        try:
            if not force_rebuild and await self._store.has_chunks_for_topic(topic_id):
                logger.info(
                    "RAG: chunks already stored for topic, skipping build",
                    topic_id=topic_id,
                )
                return 0

            # 1. Search
            enriched_query = f"{query} {niche}".strip()
            search_results: list[SearchResult] = await search(enriched_query)
            if not search_results:
                logger.warning(
                    "RAG: search returned no results; skipping build",
                    query=enriched_query,
                    topic_id=topic_id,
                )
                return 0

            # 2. Crawl
            urls = [r.url for r in search_results]
            crawled = await crawl_batch(urls)

            # 3. Extract — only non-empty HTML
            html_pairs = [(html, url) for url, html in crawled if html]
            if not html_pairs:
                logger.warning(
                    "RAG: all URLs failed to crawl; skipping build",
                    topic_id=topic_id,
                )
                return 0

            extracted: list[ExtractedContent] = extract_batch(html_pairs)
            useful = [e for e in extracted if not e.is_empty]
            if not useful:
                logger.warning(
                    "RAG: no usable content after extraction; skipping build",
                    topic_id=topic_id,
                )
                return 0

            # 4. Chunk
            chunks: list[Chunk] = []
            texts: list[str] = []
            for doc in useful:
                doc_id = str(uuid.uuid4())
                for piece in self._splitter.split_text(doc.text):
                    piece = piece.strip()
                    if len(piece) < 50:
                        continue
                    chunks.append(
                        Chunk(
                            chunk_id=str(uuid.uuid4()),
                            chunk_text=piece,
                            source_url=doc.source_url,
                            topic_id=topic_id,
                            document_id=doc_id,
                        )
                    )
                    texts.append(piece)

            if not chunks:
                logger.warning(
                    "RAG: no chunks after splitting; skipping build",
                    topic_id=topic_id,
                )
                return 0

            # 5. Embed
            vectors = await encode(texts)

            # 6. Store
            await self._store.upsert_chunks(chunks, vectors)

            logger.info(
                "RAG build complete",
                topic_id=topic_id,
                search_results=len(search_results),
                docs=len(useful),
                chunks=len(chunks),
            )
            return len(chunks)

        except Exception as exc:
            logger.warning(
                "RAG build_for_topic failed; pipeline continues without RAG",
                topic_id=topic_id,
                error=str(exc),
            )
            return 0

    # ------------------------------------------------------------------
    # Retrieve: vector search → formatted context string
    # ------------------------------------------------------------------

    async def retrieve_context(
        self,
        topic_id: str,
        query: str,
        k: int | None = None,
    ) -> str | None:
        """Retrieve the top-k most relevant chunks for *topic_id* and
        format them as a context string ready for prompt injection.

        Returns None if RAG is disabled, no chunks exist, or retrieval fails.
        """
        if not self.enabled:
            return None

        try:
            chunks = await self._store.query(
                query_text=query,
                topic_id=topic_id,
                k=k,
            )
            if not chunks:
                logger.info(
                    "RAG: no chunks found for topic; returning no context",
                    topic_id=topic_id,
                )
                return None

            lines = ["Web Research Context (verified sources):"]
            for i, chunk in enumerate(chunks, 1):
                # Truncate excerpt to keep prompt size manageable
                excerpt = chunk.chunk_text[:300].replace("\n", " ")
                lines.append(f'[{i}] "{excerpt}" (source: {chunk.source_url})')

            context = "\n".join(lines)
            logger.info(
                "RAG context retrieved",
                topic_id=topic_id,
                chunks=len(chunks),
            )
            return context

        except Exception as exc:
            logger.warning(
                "RAG retrieve_context failed; returning no context",
                topic_id=topic_id,
                error=str(exc),
            )
            return None