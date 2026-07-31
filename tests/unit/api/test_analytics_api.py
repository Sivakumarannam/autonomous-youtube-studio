"""
Unit tests for GET/POST /api/v1/analytics/{video_id}, plus unit tests for
_parse_raw_response and the primary-metric fallback path.

The YouTube Analytics API call is mocked at the AnalyticsAgentService layer
so no real HTTP requests are made in CI.
"""
import pytest

from app.agents.analytics_agent.service import _parse_raw_response
import json
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from app.database.models.analytics import Analytics
from app.database.models.script import Script, ScriptStatus, ScriptType
from app.database.models.upload import Upload, UploadStatus
from app.database.models.video import Video, VideoStatus


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------


async def _make_script(session) -> Script:
    script = Script(
        id=uuid.uuid4(),
        topic_id=uuid.uuid4(),
        channel_id=uuid.uuid4(),
        script_type=ScriptType.LONG,
        content="Analytics API test script",
        status=ScriptStatus.APPROVED,
    )
    session.add(script)
    await session.flush()
    await session.refresh(script)
    return script


async def _make_video(
    session,
    script_id: uuid.UUID,
    status: VideoStatus = VideoStatus.COMPLETE,
) -> Video:
    video = Video(
        id=uuid.uuid4(),
        script_id=script_id,
        status=status,
        resolution="1280x720",
        video_path="storage/videos/test.mp4",
        duration=15.0,
        file_size=4096,
    )
    session.add(video)
    await session.flush()
    await session.refresh(video)
    return video


async def _make_upload(
    session,
    video_id: uuid.UUID,
    status: UploadStatus = UploadStatus.PUBLISHED,
    youtube_video_id: str = "yt_abc123",
) -> Upload:
    upload = Upload(
        id=uuid.uuid4(),
        video_id=video_id,
        status=status,
        title="Test Title",
        description="Test Description",
        tags=json.dumps(["test", "video"]),
        privacy_status="private",
        youtube_video_id=youtube_video_id if status == UploadStatus.PUBLISHED else None,
        youtube_url=(
            f"https://youtube.com/watch?v={youtube_video_id}"
            if status == UploadStatus.PUBLISHED
            else None
        ),
    )
    session.add(upload)
    await session.flush()
    await session.refresh(upload)
    return upload


async def _make_analytics(session, upload_id: uuid.UUID) -> Analytics:
    snap = Analytics(
        id=uuid.uuid4(),
        upload_id=upload_id,
        snapshot_date=datetime.now(timezone.utc),
        views=1000,
        likes=80,
        comments=20,
        shares=5,
        watch_time_minutes=120.0,
        average_view_duration=45.0,
        average_view_percentage=60.0,
        ctr=0.05,
        impressions=500,
        subscribers_gained=10,
        subscribers_lost=1,
        revenue=0.0,
    )
    session.add(snap)
    await session.flush()
    await session.refresh(snap)
    return snap


# ---------------------------------------------------------------------------
# _parse_raw_response — unit tests for parser correctness
# ---------------------------------------------------------------------------


class TestParseRawResponse:
    def _make_raw(self, headers, rows):
        return {
            "columnHeaders": [{"name": h} for h in headers],
            "rows": rows,
        }

    def test_empty_rows_returns_zeros(self):
        raw = self._make_raw(["views", "likes"], [])
        result = _parse_raw_response(raw)
        assert result == {"views": 0.0, "likes": 0.0}

    def test_single_row_parsed_correctly(self):
        raw = self._make_raw(
            ["views", "likes", "impressionClickThroughRate", "averageViewDuration"],
            [[5000, 250, 0.045, 72.3]],
        )
        result = _parse_raw_response(raw)
        assert result["views"] == 5000.0
        assert result["likes"] == 250.0
        assert result["impressionClickThroughRate"] == pytest.approx(0.045)
        assert result["averageViewDuration"] == pytest.approx(72.3)

    def test_multiple_rows_uses_first_row_only(self):
        """Ratio metrics must NOT be summed across rows; we take only row[0]."""
        raw = self._make_raw(
            ["views", "impressionClickThroughRate"],
            [[1000, 0.05], [2000, 0.03]],
        )
        result = _parse_raw_response(raw)
        # First row only — not summed (3000) or averaged (0.04)
        assert result["views"] == 1000.0
        assert result["impressionClickThroughRate"] == pytest.approx(0.05)

    def test_none_values_treated_as_zero(self):
        raw = self._make_raw(["views", "likes"], [[None, None]])
        result = _parse_raw_response(raw)
        assert result["views"] == 0.0
        assert result["likes"] == 0.0

    def test_missing_rows_key_returns_zeros(self):
        raw = {"columnHeaders": [{"name": "views"}]}
        result = _parse_raw_response(raw)
        assert result == {"views": 0.0}


# ---------------------------------------------------------------------------
# AnalyticsAgentService.fetch_for_upload — fallback path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_for_upload_falls_back_to_primary_metrics(test_session):
    """When the extended metric set is rejected (4xx), service retries with primaries."""
    import uuid as _uuid
    from datetime import date, datetime, timezone
    from unittest.mock import AsyncMock, patch, MagicMock

    from app.agents.analytics_agent.service import AnalyticsAgentService
    from app.database.models.upload import Upload, UploadStatus

    upload = Upload(
        id=_uuid.uuid4(),
        video_id=_uuid.uuid4(),
        youtube_video_id="yt_xyz789",
        status=UploadStatus.PUBLISHED,
        youtube_url="https://youtube.com/watch?v=yt_xyz789",
        privacy_status="private",
    )

    extended_call_count = 0
    primary_raw = {
        "columnHeaders": [{"name": "views"}, {"name": "likes"}],
        "rows": [[999, 55]],
    }

    async def mock_fetch(video_id, start_date, end_date, metrics):
        nonlocal extended_call_count
        from app.agents.analytics_agent.service import _EXTENDED_METRICS, _PRIMARY_METRICS
        if metrics == _EXTENDED_METRICS:
            extended_call_count += 1
            raise Exception("400 unsupported metric: impressions")
        return primary_raw

    fake_auth = MagicMock()
    fake_auth.get_access_token = AsyncMock(return_value="tok")
    fake_auth.close = AsyncMock()
    fake_svc = MagicMock()
    fake_svc.fetch_video_analytics = mock_fetch
    fake_svc.close = AsyncMock()

    with patch("app.integrations.youtube.auth.YouTubeAuthManager", return_value=fake_auth), \
         patch("app.integrations.youtube.analytics.YouTubeAnalyticsService", return_value=fake_svc), \
         patch("app.agents.analytics_agent.service.AnalyticsRepository") as mock_repo_cls:
        mock_repo = MagicMock()
        saved = MagicMock()
        saved.id = _uuid.uuid4()
        saved.upload_id = upload.id
        saved.views = 999
        saved.likes = 55
        mock_repo.create = AsyncMock(return_value=saved)
        mock_repo_cls.return_value = mock_repo

        svc = AnalyticsAgentService(test_session)
        result = await svc.fetch_for_upload(
            upload=upload,
            start_date=date(2026, 6, 1),
            end_date=date(2026, 6, 30),
        )

    assert extended_call_count == 1, "Extended metrics should have been attempted once"
    assert result.views == 999


# ---------------------------------------------------------------------------
# Date-window default — service defaults to last 28 days
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_for_video_uses_default_28_day_window(test_session):
    """When no dates are supplied, AnalyticsService passes a 28-day window."""
    import uuid as _uuid
    from datetime import date, timedelta
    from unittest.mock import AsyncMock, patch, MagicMock

    from app.api.services.analytics_service import AnalyticsService
    from app.database.models.script import Script, ScriptStatus, ScriptType
    from app.database.models.upload import Upload, UploadStatus
    from app.database.models.video import Video, VideoStatus

    script = Script(
        id=_uuid.uuid4(), topic_id=_uuid.uuid4(), channel_id=_uuid.uuid4(),
        script_type=ScriptType.LONG, content="test", status=ScriptStatus.APPROVED,
    )
    test_session.add(script)
    await test_session.flush()

    video = Video(
        id=_uuid.uuid4(), script_id=script.id, status=VideoStatus.COMPLETE,
        resolution="1280x720", video_path="/tmp/t.mp4", duration=10.0, file_size=1024,
    )
    test_session.add(video)
    await test_session.flush()

    upload = Upload(
        id=_uuid.uuid4(), video_id=video.id, youtube_video_id="yt_window_test",
        status=UploadStatus.PUBLISHED, youtube_url="https://youtube.com/watch?v=yt_window_test",
        privacy_status="private",
    )
    test_session.add(upload)
    await test_session.flush()

    captured = {}

    async def fake_fetch(self_inner, upload=None, start_date=None, end_date=None):
        captured["start_date"] = start_date
        captured["end_date"] = end_date
        snap = MagicMock()
        snap.id = _uuid.uuid4()
        snap.upload_id = upload.id if upload else _uuid.uuid4()
        snap.views = 0
        return snap

    with patch(
        "app.agents.analytics_agent.service.AnalyticsAgentService.fetch_for_upload",
        new=fake_fetch,
    ):
        svc = AnalyticsService(test_session)
        await svc.fetch_for_video(video_id=video.id)

    today = date.today()
    assert captured["end_date"] == today
    assert captured["start_date"] == today - timedelta(days=28)


def _fake_fetch_for_upload(snapshot: Analytics):
    """Stand-in for AnalyticsAgentService.fetch_for_upload — returns a ready snapshot."""
    async def _run(self, upload, start_date, end_date):
        return snapshot
    return _run


# ---------------------------------------------------------------------------
# POST /api/v1/analytics/{video_id}  — fetch fresh snapshot
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_analytics_video_not_found(client: AsyncClient):
    response = await client.post(f"/api/v1/analytics/{uuid.uuid4()}")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_fetch_analytics_no_upload(client: AsyncClient, test_session):
    script = await _make_script(test_session)
    video = await _make_video(test_session, script.id)
    await test_session.commit()

    response = await client.post(f"/api/v1/analytics/{video.id}")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_fetch_analytics_upload_not_published(client: AsyncClient, test_session):
    script = await _make_script(test_session)
    video = await _make_video(test_session, script.id)
    await _make_upload(test_session, video.id, status=UploadStatus.PENDING)
    await test_session.commit()

    response = await client.post(f"/api/v1/analytics/{video.id}")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_fetch_analytics_success(client: AsyncClient, test_session):
    script = await _make_script(test_session)
    video = await _make_video(test_session, script.id)
    upload = await _make_upload(test_session, video.id)
    snapshot = await _make_analytics(test_session, upload.id)
    await test_session.commit()

    with patch(
        "app.agents.analytics_agent.service.AnalyticsAgentService.fetch_for_upload",
        new=_fake_fetch_for_upload(snapshot),
    ):
        response = await client.post(f"/api/v1/analytics/{video.id}")

    assert response.status_code == 201
    body = response.json()
    assert body["success"] is True
    assert body["analytics"]["upload_id"] == str(upload.id)
    assert body["analytics"]["views"] == 1000
    assert body["analytics"]["likes"] == 80


@pytest.mark.asyncio
async def test_fetch_analytics_with_date_range(client: AsyncClient, test_session):
    script = await _make_script(test_session)
    video = await _make_video(test_session, script.id)
    upload = await _make_upload(test_session, video.id)
    snapshot = await _make_analytics(test_session, upload.id)
    await test_session.commit()

    with patch(
        "app.agents.analytics_agent.service.AnalyticsAgentService.fetch_for_upload",
        new=_fake_fetch_for_upload(snapshot),
    ):
        response = await client.post(
            f"/api/v1/analytics/{video.id}",
            params={"start_date": "2026-06-01", "end_date": "2026-06-30"},
        )

    assert response.status_code == 201
    assert response.json()["success"] is True


# ---------------------------------------------------------------------------
# GET /api/v1/analytics/{video_id}/latest
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_latest_analytics_video_not_found(client: AsyncClient):
    response = await client.get(f"/api/v1/analytics/{uuid.uuid4()}/latest")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_latest_analytics_no_snapshot(client: AsyncClient, test_session):
    script = await _make_script(test_session)
    video = await _make_video(test_session, script.id)
    await _make_upload(test_session, video.id)
    await test_session.commit()

    response = await client.get(f"/api/v1/analytics/{video.id}/latest")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_latest_analytics_success(client: AsyncClient, test_session):
    script = await _make_script(test_session)
    video = await _make_video(test_session, script.id)
    upload = await _make_upload(test_session, video.id)
    snapshot = await _make_analytics(test_session, upload.id)
    await test_session.commit()

    response = await client.get(f"/api/v1/analytics/{video.id}/latest")
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(snapshot.id)
    assert body["upload_id"] == str(upload.id)
    assert body["views"] == 1000
    assert body["ctr"] == pytest.approx(0.05)


# ---------------------------------------------------------------------------
# GET /api/v1/analytics/{video_id}  — list snapshots
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_analytics_video_not_found(client: AsyncClient):
    response = await client.get(f"/api/v1/analytics/{uuid.uuid4()}")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_list_analytics_empty(client: AsyncClient, test_session):
    script = await _make_script(test_session)
    video = await _make_video(test_session, script.id)
    await _make_upload(test_session, video.id)
    await test_session.commit()

    response = await client.get(f"/api/v1/analytics/{video.id}")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 0
    assert body["items"] == []


@pytest.mark.asyncio
async def test_list_analytics_returns_snapshots(client: AsyncClient, test_session):
    script = await _make_script(test_session)
    video = await _make_video(test_session, script.id)
    upload = await _make_upload(test_session, video.id)
    await _make_analytics(test_session, upload.id)
    await _make_analytics(test_session, upload.id)
    await test_session.commit()

    response = await client.get(f"/api/v1/analytics/{video.id}")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert len(body["items"]) == 2
