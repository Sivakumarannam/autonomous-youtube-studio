---
name: Session refresh pipeline fix
description: Bugs introduced and fixed when _refresh_session() replaces self._session mid-pipeline; lessons for future refactors.
---

# Session Refresh Fix — Lessons

## Context
`_refresh_session()` in `PipelineAgentService` closes the current `self._session` and opens a fresh one from the pool after a long video render. This prevents asyncpg connection drops on Neon serverless Postgres.

## Bugs caught (both required code-review cycles to surface)

### 1. Stale `pipeline_repo` in `run()` exception handler
`pipeline_repo` was created once at the top of `run()` and reused across the retry loop. After `_refresh_session()`, `self._session` was replaced but `pipeline_repo` still held a reference to the closed session → retry/failed-state writes silently failed.

**Fix:** Rebuild `pipeline_repo = PipelineRunRepository(self._session)` at the top of every exception handler in `run()` and again after `asyncio.sleep(delay)`.

### 2. Cross-session `pipeline_run` instance
`_execute_stages()` re-fetches `pipeline_run` against the new session locally, but `run()`'s outer `pipeline_run` variable stays bound to the old session. Calling `self._session.refresh(pipeline_run)` on a cross-session instance raises or bypasses persistence.

**Fix:** Replace `await self._session.refresh(pipeline_run)` in the exception handler with `pipeline_run = await pipeline_repo.get_or_raise(run_id)` — always loads a fresh identity-map entry from the current session.

## Rule
> After any session replacement, treat ALL ORM instances and repo objects from the old session as invalid. Re-fetch by primary key; never refresh across sessions.

**Why:** SQLAlchemy AsyncSession identity maps are per-session. An instance loaded from session A cannot be refreshed or merged into session B without explicit re-attachment.

**How to apply:** Any time `self._session` is reassigned anywhere in PipelineAgentService, audit every code path that runs afterward for stale repo/instance references.
