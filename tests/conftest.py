import uuid
from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import AsyncMock, MagicMock
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.database.connection import Base, get_db
from app.llm_providers.base import BaseLLMProvider, LLMResponse
from app.llm_providers.mock_provider import MockLLMProvider
from app.main import app


# ---------- Event loop ----------



# ---------- In-memory test DB ----------

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

@pytest_asyncio.fixture
async def test_engine():
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest_asyncio.fixture
async def test_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
        await session.rollback()


# ---------- FastAPI test client ----------

@pytest_asyncio.fixture
async def client(test_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    async def override_get_db():
        yield test_session

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


# ---------- Dashboard/metrics auth override ----------
# The Phase 5 follow-up added a shared-secret guard on /dashboard and
# /metrics only (app/web/auth.py::require_dashboard_auth). Tests exercise
# route behavior, not the auth guard itself (that's covered separately),
# so it's overridden to a no-op here — same pattern as get_db above.

@pytest.fixture(autouse=True)
def _bypass_dashboard_auth():
    from app.web.auth import require_dashboard_auth

    app.dependency_overrides[require_dashboard_auth] = lambda: None
    yield
    app.dependency_overrides.pop(require_dashboard_auth, None)


# ---------- Mock LLM ----------

@pytest.fixture
def mock_llm() -> MockLLMProvider:
    return MockLLMProvider()


@pytest.fixture
def mock_llm_provider() -> BaseLLMProvider:
    provider = MagicMock(spec=BaseLLMProvider)
    provider.provider_name = "mock"
    provider.generate_text = AsyncMock(return_value='[{"topic": "Test Topic", "score": 90, "reason": "Test", "keywords": ["test"], "content_type": "long"}]')
    provider.generate = AsyncMock(return_value=LLMResponse(content="test", model="mock", provider="mock"))
    return provider


# ---------- Model factories ----------

def make_channel_id() -> uuid.UUID:
    return uuid.uuid4()


def make_topic_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def channel_id() -> uuid.UUID:
    return make_channel_id()


@pytest.fixture
def topic_id() -> uuid.UUID:
    return make_topic_id()


# ---------- DB object helpers ----------

async def create_test_channel(session: AsyncSession, **kwargs) -> Any:
    from app.database.models.channel import Channel
    ch = Channel(
        name=kwargs.get("name", f"Test Channel {uuid.uuid4().hex[:6]}"),
        niche=kwargs.get("niche", "technology"),
        language=kwargs.get("language", "en"),
        **{k: v for k, v in kwargs.items() if k not in ("name", "niche", "language")},
    )
    session.add(ch)
    await session.flush()
    await session.refresh(ch)
    return ch


async def create_test_topic(session: AsyncSession, channel_id: uuid.UUID, **kwargs) -> Any:
    from app.database.models.topic import Topic
    t = Topic(
        channel_id=channel_id,
        title=kwargs.get("title", f"Test Topic {uuid.uuid4().hex[:6]}"),
        score=kwargs.get("score", 80.0),
        **{k: v for k, v in kwargs.items() if k not in ("title", "score")},
    )
    session.add(t)
    await session.flush()
    await session.refresh(t)
    return t


async def create_test_research(session: AsyncSession, topic_id: uuid.UUID, **kwargs) -> Any:
    from app.database.models.research import Research, ResearchStatus
    r = Research(
        topic_id=topic_id,
        summary=kwargs.get("summary", "Test research summary"),
        key_facts=kwargs.get("key_facts", '["fact 1", "fact 2"]'),
        references=kwargs.get("references", '["https://example.com"]'),
        status=kwargs.get("status", ResearchStatus.COMPLETE),
    )
    session.add(r)
    await session.flush()
    await session.refresh(r)
    return r

@pytest.fixture
def create_test_script():

    async def _create(
        session,
        topic_id,
        channel_id,
        script_type=None,
        **kwargs,
    ):
        from app.database.models.script import Script, ScriptType

        script = Script(
            topic_id=topic_id,
            channel_id=channel_id,
            script_type=script_type or ScriptType.SHORT,
            content=kwargs.get("content", "Test Script"),
            word_count=kwargs.get("word_count", 10),
            estimated_duration=kwargs.get("estimated_duration", 30),
        )

        session.add(script)
        await session.flush()
        await session.refresh(script)

        return script

    return _create 