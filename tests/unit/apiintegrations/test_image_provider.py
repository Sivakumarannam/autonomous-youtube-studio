"""Targeted tests for app/integrations/image_provider.py.

All network I/O is mocked — no real HTTP calls are made.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FAKE_JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 100  # minimal JPEG magic bytes


def _make_response(content: bytes, content_type: str = "image/jpeg", status: int = 200):
    """Return a mock httpx.Response-like object."""
    mock = MagicMock()
    mock.content = content
    mock.headers = {"content-type": content_type}
    mock.status_code = status
    mock.raise_for_status = MagicMock()
    return mock


# ---------------------------------------------------------------------------
# ImageProvider.generate — Pollinations happy path
# ---------------------------------------------------------------------------

class TestPollinationsProvider:
    @pytest.mark.asyncio
    async def test_returns_local_path_on_success(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "app.core.config.settings.storage_local_path", str(tmp_path)
        )
        response = _make_response(_FAKE_JPEG)
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=response)

        with patch("app.integrations.image_provider.httpx.AsyncClient", return_value=mock_client):
            from app.integrations.image_provider import ImageProvider
            result = await ImageProvider.generate(
                prompt="a sunset over mountains",
                width=1280,
                height=720,
                script_id="script-abc",
            )

        assert result is not None
        assert Path(result).exists()
        assert Path(result).read_bytes() == _FAKE_JPEG

    @pytest.mark.asyncio
    async def test_cache_hit_skips_http(self, tmp_path, monkeypatch):
        """Second call with the same args must hit disk cache — HTTP not called."""
        monkeypatch.setattr(
            "app.core.config.settings.storage_local_path", str(tmp_path)
        )
        response = _make_response(_FAKE_JPEG)
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=response)

        with patch("app.integrations.image_provider.httpx.AsyncClient", return_value=mock_client):
            from app.integrations.image_provider import ImageProvider

            await ImageProvider.generate(
                prompt="cached prompt", width=640, height=360, script_id="s1"
            )
            await ImageProvider.generate(
                prompt="cached prompt", width=640, height=360, script_id="s1"
            )

        # Only one real GET, second call should have been served from cache
        assert mock_client.get.call_count == 1

    @pytest.mark.asyncio
    async def test_returns_none_when_pollinations_errors_and_no_hf_token(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setattr(
            "app.core.config.settings.storage_local_path", str(tmp_path)
        )
        monkeypatch.delenv("HF_API_TOKEN", raising=False)

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(side_effect=Exception("connection refused"))

        with patch("app.integrations.image_provider.httpx.AsyncClient", return_value=mock_client):
            from app.integrations.image_provider import ImageProvider
            result = await ImageProvider.generate(
                prompt="any prompt", width=1280, height=720, script_id="s-fail"
            )

        assert result is None

    @pytest.mark.asyncio
    async def test_empty_prompt_returns_none_immediately(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "app.core.config.settings.storage_local_path", str(tmp_path)
        )
        from app.integrations.image_provider import ImageProvider

        result = await ImageProvider.generate(
            prompt="   ", width=1280, height=720, script_id="s-empty"
        )
        assert result is None


# ---------------------------------------------------------------------------
# ImageProvider.generate — HuggingFace fallback
# ---------------------------------------------------------------------------

class TestHuggingFaceFallback:
    @pytest.mark.asyncio
    async def test_hf_not_called_when_token_absent(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "app.core.config.settings.storage_local_path", str(tmp_path)
        )
        monkeypatch.delenv("HF_API_TOKEN", raising=False)

        # Pollinations fails
        poll_client = AsyncMock()
        poll_client.__aenter__ = AsyncMock(return_value=poll_client)
        poll_client.__aexit__ = AsyncMock(return_value=False)
        poll_client.get = AsyncMock(side_effect=Exception("timeout"))

        with patch("app.integrations.image_provider.httpx.AsyncClient", return_value=poll_client):
            from app.integrations.image_provider import ImageProvider
            result = await ImageProvider.generate(
                prompt="no token test", width=512, height=512, script_id="s-nohf"
            )

        # HF post must never have been called
        assert poll_client.post.call_count == 0
        assert result is None

    @pytest.mark.asyncio
    async def test_hf_used_when_pollinations_fails_and_token_set(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setattr(
            "app.core.config.settings.storage_local_path", str(tmp_path)
        )
        monkeypatch.setenv("HF_API_TOKEN", "hf-test-token")

        call_count = {"poll": 0, "hf": 0}

        async def _client_get(*args, **kwargs):
            call_count["poll"] += 1
            raise Exception("pollinations down")

        async def _client_post(*args, **kwargs):
            call_count["hf"] += 1
            return _make_response(_FAKE_JPEG)

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(side_effect=_client_get)
        mock_client.post = AsyncMock(side_effect=_client_post)

        with patch("app.integrations.image_provider.httpx.AsyncClient", return_value=mock_client):
            from app.integrations.image_provider import ImageProvider
            result = await ImageProvider.generate(
                prompt="hf fallback scene", width=512, height=512, script_id="s-hf"
            )

        assert result is not None
        assert Path(result).exists()
        assert call_count["hf"] >= 1


# ---------------------------------------------------------------------------
# Cache-path determinism
# ---------------------------------------------------------------------------

class TestCachePath:
    def test_same_args_yield_same_path(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "app.core.config.settings.storage_local_path", str(tmp_path)
        )
        from app.integrations.image_provider import ImageProvider

        p1 = ImageProvider._cache_path("s1", "sunset", 1280, 720)
        p2 = ImageProvider._cache_path("s1", "sunset", 1280, 720)
        assert p1 == p2

    def test_different_prompts_yield_different_paths(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "app.core.config.settings.storage_local_path", str(tmp_path)
        )
        from app.integrations.image_provider import ImageProvider

        p1 = ImageProvider._cache_path("s1", "sunset", 1280, 720)
        p2 = ImageProvider._cache_path("s1", "moonrise", 1280, 720)
        assert p1 != p2

    def test_different_script_ids_yield_different_dirs(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "app.core.config.settings.storage_local_path", str(tmp_path)
        )
        from app.integrations.image_provider import ImageProvider

        p1 = ImageProvider._cache_path("script-A", "x", 1280, 720)
        p2 = ImageProvider._cache_path("script-B", "x", 1280, 720)
        assert p1.parent != p2.parent


# ---------------------------------------------------------------------------
# Concurrent requests — cache race condition regression test
# ---------------------------------------------------------------------------

class TestConcurrentRequests:
    @pytest.mark.asyncio
    async def test_concurrent_identical_requests_call_provider_once(
        self, tmp_path, monkeypatch
    ):
        """Ten concurrent generate() calls for the same prompt must result in
        exactly one provider HTTP call — subsequent callers must wait behind
        the in-process lock and find the cache populated.
        """
        import asyncio
        monkeypatch.setattr(
            "app.core.config.settings.storage_local_path", str(tmp_path)
        )
        monkeypatch.delenv("HF_API_TOKEN", raising=False)

        # Reset module-level lock registry so this test is isolated
        import app.integrations.image_provider as ip_mod
        ip_mod._cache_locks.clear()

        call_count = {"n": 0}

        async def fake_get(*args, **kwargs):
            call_count["n"] += 1
            # Simulate a short network delay so coroutines actually overlap
            await asyncio.sleep(0.05)
            return _make_response(_FAKE_JPEG)

        mock_client = type("MC", (), {
            "__aenter__": lambda s: asyncio.coroutine(lambda: s)(),
            "__aexit__": lambda s, *a: asyncio.coroutine(lambda: False)(),
            "get": None,
        })()

        class FakeAsyncClient:
            def __init__(self, **kw): pass
            async def __aenter__(self): return self
            async def __aexit__(self, *a): return False
            async def get(self, *a, **kw):
                call_count["n"] += 1
                await asyncio.sleep(0.05)
                return _make_response(_FAKE_JPEG)

        with patch("app.integrations.image_provider.httpx.AsyncClient", FakeAsyncClient):
            from app.integrations.image_provider import ImageProvider

            results = await asyncio.gather(*[
                ImageProvider.generate(
                    prompt="identical concurrent prompt",
                    width=512,
                    height=512,
                    script_id="concurrent-test",
                )
                for _ in range(10)
            ])

        # All 10 must return the same valid path
        assert all(r is not None for r in results)
        assert len(set(results)) == 1, "All coroutines must resolve to the same cached file"
        # Exactly one provider call was made
        assert call_count["n"] == 1, (
            f"Expected 1 provider call, got {call_count['n']} — cache lock not working"
        )
