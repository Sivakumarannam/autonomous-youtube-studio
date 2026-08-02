# Studio Assistant Chatbot — Design Report

**Project:** Autonomous YouTube Studio  
**Document version:** 2026-08-02  
**Status:** Awaiting approval before implementation

---

## 1. What This Project Does (System Summary)

**Autonomous YouTube Studio** is a fully automated content factory that produces and publishes YouTube videos with zero manual work after initial setup.

The pipeline runs on a schedule:

```
Topic Discovery
    ↓
Web Research (RAG — crawl + embed + vector search)
    ↓
Script Writing (Groq LLM, Gemini fallback)
    ↓
Quality & Moderation checks (auto-reject bad content)
    ↓
SEO optimisation (titles, descriptions, tags)
    ↓
Voice narration (Kokoro TTS primary, gTTS fallback)
    ↓
Storyboard → Scene cards with stock images/AI images
    ↓
Video render (FFmpeg — karaoke captions, background music, transitions)
    ↓
Thumbnail generation
    ↓
YouTube upload (OAuth)
    ↓
Instagram cross-post (Business Login token)
    ↓
Notifications (Slack / Telegram / Discord / Email)
```

Everything runs automatically. The operator dashboard shows live pipeline status via WebSocket.

---

## 2. Why a Chatbot

Right now, if something in the pipeline breaks or an operator wants to know "why did the last video fail?" they have to:
1. Open the dashboard
2. Find the pipeline run
3. Read raw log entries
4. Cross-reference scheduler status panels

This requires knowing the system internals. The chatbot replaces that with a plain-English question interface — **ask anything about the studio, get an answer from the system's own data and knowledge**.

Additionally, when the chatbot doesn't know the answer, it shouldn't silently fail. It escalates to the real agent (this system) which can investigate and fix it.

---

## 3. Chatbot Architecture

### 3.1 Two-Layer Answer Engine

Every user question goes through two layers in sequence:

```
User question
    ↓
Layer 1 — Knowledge Base (static docs)
    RAG search over ingested project documentation,
    FAQs, how-it-works guides (FAISS vector store,
    topic_id = "studio_knowledge")
    ↓
Layer 2 — Live DB Context (dynamic state)
    Auto-injected: recent pipeline runs, upload status,
    scheduler health, active channels, error summaries
    ↓
LLM synthesis (Groq → Gemini fallback)
    ↓
Answer streamed to dashboard via WebSocket
    ↓
(If unresolved) → Escalation Agent
```

### 3.2 Escalation Path

If the LLM returns a low-confidence answer (signalled by a structured JSON flag in the response) or the user explicitly says "this didn't help", the system:

1. Saves the question + context as a `ChatUnresolved` database record
2. Sends a notification (Slack/Telegram/Discord — whichever is configured) with the question
3. Shows the user: *"I've flagged this for investigation. You'll receive a notification when it's resolved."*
4. The human (or agent in a future turn) can mark it resolved, and the resolution gets ingested back into the knowledge base automatically

### 3.3 Knowledge Base Structure

The existing `VectorStore` (FAISS + SQLite) already supports per-topic isolation via `topic_id`. The chatbot uses a reserved namespace:

| topic_id | Contents |
|---|---|
| `studio_knowledge` | Project docs, FAQs, how-to guides |
| `studio_resolved_qa` | Past resolved escalations (grows over time) |
| *(all other topic_ids)* | Video research — untouched, no crossover |

Documents in the knowledge base are tracked in a new `KnowledgeDoc` database table (title, source, ingested_at, chunk_count, active).

### 3.4 WebSocket Transport

The project already has:
- `ConnectionManager` singleton (`app/websocket/manager.py`)
- `/ws/pipeline` endpoint with cookie auth

The chatbot adds:
- `/ws/chat` — bidirectional: client sends `{"type":"question","text":"..."}`, server streams back `{"type":"token","text":"..."}` chunks, then `{"type":"done","sources":[...]}` 

This matches the existing HTMX + WebSocket pattern in `base.html` exactly.

### 3.5 Document Management

A new dashboard panel **"Knowledge Base"** allows:

- **Upload a document** — paste text or upload `.txt` / `.md` / `.pdf` → chunked, embedded, stored
- **View documents** — list all ingested docs with title, date, chunk count, status
- **Delete a document** — removes all chunks from FAISS + SQLite for that doc
- **Preview chunks** — see what the chatbot "knows" from a given document

This is fully self-service. No redeploy required when you update docs.

---

## 4. What the Chatbot Can Answer

### Category A — Project knowledge (from documents)
- "What is the full pipeline flow?"
- "How does the karaoke caption system work?"
- "What happens when the Instagram token expires?"
- "What does the quality agent check for?"
- "How do I add a new channel?"

### Category B — Live system state (from database)
- "What's running right now?"
- "Why did the last pipeline fail?"
- "How many videos were uploaded this week?"
- "Which channel has the most content?"
- "What's in the upload queue?"
- "Is the scheduler healthy?"
- "When is the next scheduled run?"

### Category C — Troubleshooting (RAG + live context combined)
- "The video render failed — what should I check?"
- "Instagram cross-posting stopped working, why?"
- "The voice sounds wrong on the last video — what changed?"

### Category D — Escalations (unknown → agent)
- "Can you add support for TikTok?" → Escalated, task created
- "The pipeline is stuck and restarting didn't fix it" → Escalated with full context

---

## 5. Dashboard UI Design

### Chat Panel (new, full-width, below existing panels)

```
┌─────────────────────────────────────────────────────────────┐
│  STUDIO ASSISTANT                          ● Live  [Docs ↗] │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  Hello! I know everything about this studio —        │   │
│  │  the pipeline, your channels, recent runs, and       │   │
│  │  how every agent works. Ask me anything.            │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  [User]  Why did the last pipeline run fail?               │
│                                                             │
│  [Bot ▌] The last run for channel "Tech Talks" failed      │
│          at the Video stage (08:42 UTC). The error was:     │
│          FFmpeg exit code 1 — audio file not found at       │
│          storage/voice/.... This usually means the Voice    │
│          agent finished but didn't write the file path to   │
│          the DB before the Video agent read it.             │
│                                                             │
│          Sources: [Pipeline Run #47] [Voice Agent Docs]     │
│                                                    [Flag ↑] │
├─────────────────────────────────────────────────────────────┤
│  Ask anything about the studio…              [Send ↵]      │
└─────────────────────────────────────────────────────────────┘
```

- **Streaming tokens** appear character-by-character (WebSocket chunks)
- **Sources** shown below each answer (which doc or DB record was used)
- **Flag button** (↑) manually escalates any answer the user isn't satisfied with
- **Docs link** opens the Knowledge Base management panel
- **Suggested questions** shown on first load as clickable chips

### Knowledge Base Panel (separate section)

```
┌──────────────────────────────────────────────────────────────┐
│  KNOWLEDGE BASE                         [+ Upload Document]  │
├──────────────────────────────────────────────────────────────┤
│  Title                       Chunks  Uploaded      Actions   │
│  ─────────────────────────── ──────  ──────────    ──────    │
│  Project Overview & Pipeline   42    2026-08-02    [Delete]  │
│  Agent Descriptions & Roles    38    2026-08-02    [Delete]  │
│  Troubleshooting Guide         27    2026-08-02    [Delete]  │
│  Instagram Token Renewal FAQ   11    2026-08-02    [Delete]  │
└──────────────────────────────────────────────────────────────┘
```

---

## 6. New Files to Create

| File | Purpose |
|---|---|
| `app/chatbot/__init__.py` | Module init |
| `app/chatbot/knowledge_base.py` | Ingest / delete documents into vector store under `studio_knowledge` namespace |
| `app/chatbot/context_builder.py` | Query live DB (recent runs, uploads, errors) and build context string |
| `app/chatbot/engine.py` | Main answer engine: RAG retrieval → context merge → LLM call → stream tokens |
| `app/chatbot/escalation.py` | Save `ChatUnresolved` record, fire notification |
| `app/database/models/chat.py` | `ChatUnresolved` model, `KnowledgeDoc` model |
| `app/database/migrations/versions/20260802_001_add_chat_models.py` | Alembic migration |
| `app/api/routes/chat.py` | `/ws/chat` WebSocket + REST endpoints for KB management |
| `app/templates/dashboard/_chat.html` | Chat panel partial |
| `app/templates/dashboard/_knowledge_base.html` | KB management partial |
| `docs/project_overview.md` | First document to ingest into KB (auto-seeded on startup) |

### Modified Files

| File | Change |
|---|---|
| `app/main.py` | Mount chat router; auto-seed KB docs on startup if empty |
| `app/api/routes/websocket.py` | Add `/ws/chat` route |
| `app/templates/dashboard/index.html` | Add chat panel + KB panel sections |
| `app/templates/base.html` | Add chat CSS; extend WS message handler for `chat_token` events |

---

## 7. User-Perspective Improvements (Recommendations)

These are improvements beyond the base chatbot, ordered by user impact:

### High impact
1. **Suggested questions on load** — show 4–6 clickable question chips based on current system state (e.g. "Why did the last run fail?" if a recent failure exists). Removes the blank-page problem.
2. **Answer confidence indicator** — show a subtle badge (✓ Confident / ⚠ Uncertain) so the user knows when to verify manually.
3. **Auto-resolve loop** — when an escalation is resolved (by the human), the resolution is auto-ingested back into the KB so the same question is answered autonomously next time.

### Medium impact
4. **Persistent conversation history** — store the last 20 messages per session in a `chat_history` table so context carries across page refreshes.
5. **Export chat as markdown** — download the full conversation for documentation or debugging records.
6. **Keyboard shortcut** — `Ctrl+/` or `Cmd+K` to focus the chat input from anywhere in the dashboard.

### Nice to have
7. **Voice input** — browser `SpeechRecognition` API to dictate questions (zero new dependencies).
8. **Proactive alerts** — chatbot posts a message automatically when a pipeline fails, an Instagram token is about to expire, or the disk is >80% full.

---

## 8. What Is NOT Included (Scope Boundary)

- No external chat UI (Slack bot, Telegram bot) — dashboard-only in this task
- No multi-user conversation isolation (single-operator assumption matches the rest of the app)
- No fine-tuning of the LLM — prompt engineering only
- No paid embeddings API — uses existing `all-MiniLM-L6-v2` (already installed)

---

## 9. Implementation Order

1. DB models + Alembic migration
2. `knowledge_base.py` (ingest/delete docs) + seed `docs/project_overview.md`
3. `context_builder.py` (live DB queries)
4. `engine.py` (RAG → LLM → stream)
5. `escalation.py` (unresolved handler)
6. `/ws/chat` WebSocket endpoint
7. REST endpoints for KB management (list, upload, delete)
8. Dashboard templates (chat panel + KB panel)
9. Auto-seed on startup + suggested questions

Estimated: ~500 lines of new code across 10 files.

---

*Awaiting your approval to begin implementation.*
