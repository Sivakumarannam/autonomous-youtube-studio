"""Chatbot Answer Engine.

Flow per question:
  1. RAG retrieval from vector store (topic_id=studio_knowledge) — optional
  2. Live DB context injection
  3. LLM call (Groq → Gemini fallback via existing FallbackProvider)
  4. Stream response word-by-word via caller-supplied async callback
  5. Return sources list + low_confidence flag
"""
from __future__ import annotations

import asyncio
from typing import Callable, Awaitable

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.llm_providers.factory import get_llm_provider
from app.llm_providers.base import LLMMessage

try:
    from app.rag.vector_store import get_vector_store, Chunk
except ImportError:
    get_vector_store = None  # type: ignore[assignment]

    class Chunk:  # type: ignore[no-redef]
        chunk_text: str = ""
        source_url: str = ""

from app.chatbot.context_builder import build_live_context
from app.chatbot.knowledge_base import TOPIC_KNOWLEDGE, TOPIC_RESOLVED_QA

logger = get_logger(__name__)

_SYSTEM_PROMPT = """You are the Studio Assistant for an Autonomous YouTube Studio — a system that
automatically generates and publishes YouTube videos. You have two sources of knowledge:

1. KNOWLEDGE BASE: curated documentation about the system's pipeline, agents, and configuration.
2. LIVE STATE: real-time data from the database (pipeline runs, uploads, scheduler, channels).

Your job is to answer the operator's questions clearly and concisely. Use both sources.
When quoting from the live state, be specific (use IDs, stages, error messages).
If you are uncertain or lack sufficient information to answer reliably, end your response
with the exact marker: __LOW_CONFIDENCE__

Keep answers under 300 words. Use markdown formatting (bold, bullet points) for clarity.
Never make up pipeline run IDs, video titles, or error messages — only use what is in the context.
For pure greetings (hi, hello, hey), reply briefly and warmly — do NOT dump system status
and do NOT use __LOW_CONFIDENCE__."""


async def answer_question(
    question: str,
    session: AsyncSession,
    on_token: Callable[[str], Awaitable[None]],
    history: list[dict] | None = None,
) -> tuple[list[dict], bool]:
    """Generate and stream an answer to *question*.

    Calls *on_token(text)* for each streamed chunk.

    Returns:
        (sources, low_confidence)
    """
    sources: list[dict] = []

    # Friendly greetings — never escalate / no live-status dump
    q = (question or "").strip().lower()
    _greetings = {
        "hi",
        "hi!",
        "hello",
        "hello!",
        "hey",
        "hey!",
        "good morning",
        "good afternoon",
        "good evening",
        "howdy",
        "yo",
        "sup",
        "hi there",
        "hello there",
    }
    if q in _greetings or q.rstrip("!.") in _greetings:
        reply = (
            "Hi! 👋 I'm the **Studio Assistant**. "
            "How can I help you today?\n\n"
            "You can ask about pipelines, uploads, channels, scheduler, "
            'or say things like *"what\'s in the queue?"*.'
        )
        words = reply.split(" ")
        for i, word in enumerate(words):
            chunk = word if i == len(words) - 1 else word + " "
            await on_token(chunk)
            if i % 8 == 0:
                await asyncio.sleep(0)
        return [], False

    # 1. RAG retrieval (skipped on free-tier without faiss / sentence-transformers)
    rag_chunks: list = []
    try:
        if get_vector_store is None:
            raise RuntimeError("RAG vector store unavailable")
        store = get_vector_store()
        rag_chunks = await store.query(question, topic_id=TOPIC_KNOWLEDGE, k=5)
        resolved_chunks = await store.query(question, topic_id=TOPIC_RESOLVED_QA, k=2)
        rag_chunks = rag_chunks + resolved_chunks
    except Exception as exc:
        logger.warning("RAG retrieval failed", error=str(exc))

    # 2. Live DB context
    live_context = ""
    try:
        live_context = await build_live_context(session)
    except Exception as exc:
        logger.warning("Live context build failed", error=str(exc))

    # 3. Build prompt
    kb_text = ""
    if rag_chunks:
        kb_text = "\n\n".join(
            f"[KB Source {i+1}: {c.source_url}]\n{c.chunk_text}"
            for i, c in enumerate(rag_chunks)
        )
        sources = [
            {"title": c.source_url.split("/")[-1], "type": "knowledge_base"}
            for c in rag_chunks[:3]
        ]

    if live_context:
        sources.append({"title": "Live system state", "type": "database"})

    context_block = ""
    if kb_text:
        context_block += f"\n\n## Knowledge Base\n{kb_text}"
    if live_context:
        context_block += f"\n\n## Live System State\n{live_context}"

    messages: list[LLMMessage] = []

    if history:
        for msg in history[-6:]:
            messages.append(LLMMessage(role=msg["role"], content=msg["content"]))

    user_content = f"Question: {question}\n{context_block}"
    messages.append(LLMMessage(role="user", content=user_content))

    try:
        provider = get_llm_provider()
        response = await provider.generate(
            messages=messages,
            system=_SYSTEM_PROMPT,
            temperature=0.3,
            max_tokens=600,
        )
        full_text = response.content
    except Exception as exc:
        logger.error("LLM call failed in chatbot engine", error=str(exc))
        full_text = (
            "I'm unable to answer right now — the language model returned an error. "
            "Please try again. __LOW_CONFIDENCE__"
        )

    low_confidence = "__LOW_CONFIDENCE__" in full_text
    display_text = full_text.replace("__LOW_CONFIDENCE__", "").strip()

    words = display_text.split(" ")
    for i, word in enumerate(words):
        chunk = word if i == len(words) - 1 else word + " "
        await on_token(chunk)
        if i % 8 == 0:
            await asyncio.sleep(0)

    return sources, low_confidence
