# Phase 4 — RAG Research Progress

## Status: COMPLETE ✅

All 6 items built, tested, and integrated. Full test suite: **804 passed, 3 pre-existing
failures** (PIL/Pillow not installed — `test_video_renderer.py`, unrelated to Phase 4).

---

## Item 1: Search Agent ✅

**Files:**
- `app/rag/search.py`

**What it does:**
- Default: DuckDuckGo HTML endpoint (no API key, no rate-limit cost)
- Config-swappable to Serper (`SERPER_API_KEY`) or Brave (`BRAVE_API_KEY`)
- Returns `list[SearchResult(url, title, snippet)]`
- Async via `httpx.AsyncClient`

**Tests:** `tests/unit/rag/test_search.py` — 19 tests covering DDG parsing,
Serper, Brave, routing logic, max_results override.

---

## Item 2: Web Crawler ✅

**Files:**
- `app/rag/crawler.py`

**What it does:**
- `crawl(url)` fetches raw HTML, respects `robots.txt` (cached per domain)
- Retry logic reuses `is_retryable_error()` from `app/utils/retry.py` — no
  second retry system built
- Per-URL failure isolation: failed URLs return `""`, never raise
- `crawl_batch(urls)` runs all URLs concurrently via `asyncio.gather`

**Tests:** `tests/unit/rag/test_crawler.py` — 13 tests covering robots.txt
allow/block, success path, retry-then-succeed, retry exhaustion, batch isolation.

---

## Item 3: Content Extractor ✅

**Files:**
- `app/rag/extractor.py`

**What it does:**
- `extract(html, source_url)` → `ExtractedContent(text, title, source_url)`
- Pass 1: `trafilatura.extract()` — article-aware boilerplate removal
- Pass 2: BeautifulSoup `<p>` join fallback if trafilatura yields < 50 chars
- `is_empty` property signals < 50 chars of usable content
- `extract_batch(items)` isolates per-item exceptions

**Tests:** `tests/unit/rag/test_extractor.py` — 12 tests covering trafilatura
success, fallback on None/exception, title extraction, batch isolation.

---

## Item 4: Embeddings ✅

**Files:**
- `app/rag/embeddings.py`

**Model:** `all-MiniLM-L6-v2` (sentence-transformers)
- 22M params, ~80 MB — fits comfortably on i5-1135G7 / 15.7 GB RAM
- Confirmed: `dim: 384` on this hardware
- L2-normalised output → inner-product == cosine similarity
- Lazy-loaded and cached at module level
- `encode(texts)` runs in thread-pool executor (never blocks the event loop)

**Tests:** `tests/unit/rag/test_embeddings.py` — 7 tests covering empty input,
vector count, dimension=384, normalisation, model cached after first load.

---

## Item 5: Vector Database ✅

**Files:**
- `app/rag/vector_store.py`

**Backend:** FAISS (IndexFlatIP) + SQLite
- chromadb blocked by Replit package firewall → FAISS is the correct choice:
  no server, local, battle-tested (Meta/Facebook)
- Persists to `storage/vector_db/vectors.index` (FAISS) + `metadata.db` (SQLite)
- Topic isolation via SQLite `topic_id` column; FAISS searched broadly then
  post-filtered — correct and efficient for expected dataset sizes
- `asyncio.Lock` on all FAISS mutations; embedding runs outside the lock
- `upsert_chunks` is idempotent (skips duplicate `chunk_id`)

**Tests:** `tests/unit/rag/test_vector_store.py` — 16 tests covering
`has_chunks_for_topic`, upsert idempotency, query filtering, k-limit, score
ordering, topic deletion, disk persistence across close/reopen.

---

## Item 6: RAG Research Service ✅

**Files:**
- `app/rag/rag_research_service.py`
- `app/rag/__init__.py`

**Modified existing files (additive only, no rewrites):**
- `app/core/config.py` — 9 new RAG settings (all with safe defaults)
- `app/agents/short_script_agent/prompts.py` — `rag_context: str | None = None`
  added to `build_short_script_prompt()`
- `app/agents/long_script_agent/prompts.py` — same for `build_long_script_prompt()`
- `app/agents/short_script_agent/agent.py` — `rag_context` threaded through
  `run()` → `_generate()` → prompt builder
- `app/agents/long_script_agent/agent.py` — same
- `app/agents/short_script_agent/service.py` — builds + retrieves RAG context
  if `rag_research_enabled=True`; wraps in try/except (fail-safe)
- `app/agents/long_script_agent/service.py` — same

**Config (all in `.env` or environment):**
```
RAG_RESEARCH_ENABLED=false        # master on/off switch (default: off)
RAG_SEARCH_MAX_RESULTS=5
RAG_CRAWL_TIMEOUT_SECONDS=10
RAG_CHUNK_SIZE=500
RAG_CHUNK_OVERLAP=50
RAG_CHUNKS_PER_TOPIC=3
RAG_VECTOR_DB_PATH=./storage/vector_db
SERPER_API_KEY=                   # optional; leave blank for DuckDuckGo
BRAVE_API_KEY=                    # optional
```

**Fail-safe guarantees:**
- Disabled by default — existing pipelines unaffected
- Any exception (search down, crawl fail, embed error) is caught, logged as
  WARNING, and returns `None` — script generation proceeds without RAG context

**Tests:** `tests/unit/rag/test_rag_research_service.py` — 16 tests covering
enabled/disabled routing, successful build pipeline, all early-exit paths (empty
search, crawl failure, extraction failure, chunk failure), exception swallowing,
retrieve returning `None` when disabled/empty/error, formatted context string.

---

## New Packages Installed

| Package            | Version | Notes                                    |
|--------------------|---------|------------------------------------------|
| trafilatura        | 2.1.0   | HTML boilerplate removal (Item 3)        |
| sentence-transformers | 5.6.0 | Embeddings, all-MiniLM-L6-v2 (Item 4)  |
| faiss-cpu          | 1.14.3  | Vector store (Item 5; chromadb blocked)  |
| beautifulsoup4     | 4.15.0  | Already in requirements.txt; installed   |
| lxml               | 6.1.1   | Already in requirements.txt; installed   |
| langchain-text-splitters | 1.1.2 | Already in requirements.txt; installed |

---

## Post-code-review fix

Code review found: each `RagResearchService()` instantiated its own `VectorStore()`
with its own `asyncio.Lock`, so concurrent requests had non-coordinating locks
and would corrupt the shared FAISS/SQLite files.

Fix applied:
- `app/rag/vector_store.py` — added `get_vector_store()` singleton + `close_vector_store()`
- `app/rag/rag_research_service.py` — uses `get_vector_store()` instead of `VectorStore()`
- `app/main.py` — calls `close_vector_store()` in lifespan shutdown sequence

Tests still pass explicit mock stores (dependency-injection friendly) so 0 tests changed.

## Full Test Suite Summary (post-Phase 4 + fix)

```
804 passed, 3 failed (pre-existing PIL), 2 skipped, 5 warnings
```

Pre-existing failures (not related to Phase 4):
- `test_video_renderer.py` × 3 — `ModuleNotFoundError: No module named 'PIL'`

---

## Phase 4 Complete

All 6 items operational. To enable RAG for a pipeline run:

```bash
export RAG_RESEARCH_ENABLED=true
```

The next pipeline run will search → crawl → extract → embed → store for each
topic, then inject retrieved context into the script generation prompt.
