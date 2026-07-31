"""Unit tests for QualityReportRepository."""
import uuid

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.quality_report import QualityReport, QualityStatus
from app.database.models.script import Script, ScriptType, ScriptStatus
from app.database.repositories.quality_report_repository import QualityReportRepository
from tests.conftest import create_test_channel, create_test_topic


async def _make_script(session, topic, channel, **kwargs) -> Script:
    script = Script(
        topic_id=topic.id,
        channel_id=channel.id,
        script_type=kwargs.get("script_type", ScriptType.LONG),
        content="Script content for quality testing",
        word_count=kwargs.get("word_count", 1000),
        estimated_duration=480,
        status=ScriptStatus.DRAFT,
    )
    session.add(script)
    await session.flush()
    await session.refresh(script)
    return script


async def _make_report(
    session,
    script: Script,
    *,
    overall_score: float = 80.0,
    passed: bool = True,
    status: QualityStatus = QualityStatus.PASSED,
    **kwargs,
) -> QualityReport:
    report = QualityReport(
        script_id=script.id,
        grammar_score=kwargs.get("grammar_score", 85.0),
        fact_consistency_score=kwargs.get("fact_consistency_score", 80.0),
        engagement_score=kwargs.get("engagement_score", 78.0),
        retention_score=kwargs.get("retention_score", 75.0),
        seo_score=kwargs.get("seo_score", 82.0),
        uniqueness_score=kwargs.get("uniqueness_score", 70.0),
        readability_score=kwargs.get("readability_score", 88.0),
        overall_score=overall_score,
        passed=passed,
        status=status,
        feedback=kwargs.get("feedback", "Good script overall."),
    )
    session.add(report)
    await session.flush()
    await session.refresh(report)
    return report


@pytest_asyncio.fixture
async def channel(test_session):
    return await create_test_channel(test_session, name=f"qr-{uuid.uuid4().hex[:6]}")


@pytest_asyncio.fixture
async def topic(test_session, channel):
    return await create_test_topic(test_session, channel.id, title=f"QR Topic {uuid.uuid4().hex[:6]}")


@pytest_asyncio.fixture
async def script(test_session, topic, channel):
    return await _make_script(test_session, topic, channel)


@pytest_asyncio.fixture
async def repo(test_session: AsyncSession) -> QualityReportRepository:
    return QualityReportRepository(test_session)


# ──────────────────────────────────────────────────────────────────────────────
# Create
# ──────────────────────────────────────────────────────────────────────────────

class TestQualityReportRepositoryCreate:
    async def test_create_report(self, test_session, script, repo):
        report = QualityReport(
            script_id=script.id,
            grammar_score=90.0,
            overall_score=85.0,
            passed=True,
            status=QualityStatus.PASSED,
        )
        created = await repo.create(report)
        assert created.id is not None
        assert created.overall_score == 85.0
        assert created.passed is True

    async def test_create_failed_report(self, test_session, script, repo):
        report = QualityReport(
            script_id=script.id,
            overall_score=45.0,
            passed=False,
            status=QualityStatus.FAILED,
            feedback="Script needs significant improvement.",
        )
        created = await repo.create(report)
        assert created.passed is False
        assert created.status == QualityStatus.FAILED

    async def test_create_needs_review_report(self, test_session, script, repo):
        report = QualityReport(
            script_id=script.id,
            overall_score=65.0,
            passed=False,
            status=QualityStatus.NEEDS_REVIEW,
        )
        created = await repo.create(report)
        assert created.status == QualityStatus.NEEDS_REVIEW

    async def test_create_multiple_reports_for_script(self, test_session, script, repo):
        """Multiple quality reports allowed per script (regeneration)."""
        await _make_report(test_session, script, overall_score=60.0, passed=False, status=QualityStatus.FAILED)
        await _make_report(test_session, script, overall_score=85.0, passed=True, status=QualityStatus.PASSED)
        reports = await repo.get_by_script_id(script.id)
        assert len(reports) == 2


# ──────────────────────────────────────────────────────────────────────────────
# Get
# ──────────────────────────────────────────────────────────────────────────────

class TestQualityReportRepositoryGet:
    async def test_get_by_id(self, test_session, script, repo):
        report = await _make_report(test_session, script)
        fetched = await repo.get_by_id(report.id)
        assert fetched is not None
        assert fetched.id == report.id

    async def test_get_by_id_missing_returns_none(self, test_session, repo):
        assert await repo.get_by_id(uuid.uuid4()) is None

    async def test_get_by_id_or_raise_missing(self, test_session, repo):
        from app.core.exceptions import NotFoundError
        with pytest.raises(NotFoundError):
            await repo.get_by_id_or_raise(uuid.uuid4())

    async def test_get_by_script_id_returns_all(self, test_session, script, repo):
        await _make_report(test_session, script, overall_score=70.0, passed=False, status=QualityStatus.FAILED)
        await _make_report(test_session, script, overall_score=88.0)
        reports = await repo.get_by_script_id(script.id)
        assert len(reports) == 2

    async def test_get_by_script_id_empty(self, test_session, script, repo):
        reports = await repo.get_by_script_id(script.id)
        assert reports == [] or len(reports) == 0

    async def test_get_latest_for_script(self, test_session, script, repo):
        await _make_report(test_session, script, overall_score=60.0, passed=False, status=QualityStatus.FAILED)
        latest_score = 92.0
        await _make_report(test_session, script, overall_score=latest_score)
        latest = await repo.get_latest_for_script(script.id)
        assert latest is not None
        assert latest.overall_score == latest_score

    async def test_get_latest_for_script_none(self, test_session, script, repo):
        result = await repo.get_latest_for_script(script.id)
        assert result is None

    async def test_get_by_status_passed(self, test_session, script, repo):
        await _make_report(test_session, script)
        passed_reports = await repo.get_by_status(QualityStatus.PASSED)
        assert all(r.status == QualityStatus.PASSED for r in passed_reports)

    async def test_get_by_status_failed(self, test_session, script, repo):
        await _make_report(test_session, script, overall_score=40.0, passed=False, status=QualityStatus.FAILED)
        failed_reports = await repo.get_by_status(QualityStatus.FAILED)
        assert len(failed_reports) >= 1
        assert all(r.status == QualityStatus.FAILED for r in failed_reports)

    async def test_get_passed(self, test_session, script, repo):
        await _make_report(test_session, script)
        results = await repo.get_passed()
        assert len(results) >= 1

    async def test_get_failed(self, test_session, script, repo):
        await _make_report(test_session, script, overall_score=30.0, passed=False, status=QualityStatus.FAILED)
        results = await repo.get_failed()
        assert len(results) >= 1


# ──────────────────────────────────────────────────────────────────────────────
# Script pass/fail checks
# ──────────────────────────────────────────────────────────────────────────────

class TestQualityReportScriptPassedCheck:
    async def test_script_has_passed_true(self, test_session, script, repo):
        await _make_report(test_session, script, passed=True)
        result = await repo.script_has_passed(script.id)
        assert result is True

    async def test_script_has_passed_false_when_only_failed(self, test_session, script, repo):
        await _make_report(test_session, script, overall_score=40.0, passed=False, status=QualityStatus.FAILED)
        result = await repo.script_has_passed(script.id)
        assert result is False

    async def test_script_has_passed_false_when_no_reports(self, test_session, script, repo):
        result = await repo.script_has_passed(script.id)
        assert result is False

    async def test_script_has_passed_true_even_with_old_failure(self, test_session, script, repo):
        """If any report passed, returns True regardless of previous failures."""
        await _make_report(test_session, script, overall_score=40.0, passed=False, status=QualityStatus.FAILED)
        await _make_report(test_session, script, overall_score=90.0, passed=True)
        result = await repo.script_has_passed(script.id)
        assert result is True


# ──────────────────────────────────────────────────────────────────────────────
# Update / Delete
# ──────────────────────────────────────────────────────────────────────────────

class TestQualityReportRepositoryUpdateDelete:
    async def test_update_feedback(self, test_session, script, repo):
        report = await _make_report(test_session, script)
        updated = await repo.update(report, feedback="Updated feedback text")
        assert updated.feedback == "Updated feedback text"

    async def test_update_score(self, test_session, script, repo):
        report = await _make_report(test_session, script, overall_score=60.0, passed=False, status=QualityStatus.FAILED)
        updated = await repo.update(report, overall_score=88.0, passed=True, status=QualityStatus.PASSED)
        assert updated.overall_score == 88.0
        assert updated.passed is True
        assert updated.status == QualityStatus.PASSED

    async def test_delete_report(self, test_session, script, repo):
        report = await _make_report(test_session, script)
        await repo.delete(report)
        assert await repo.get_by_id(report.id) is None

    async def test_delete_by_id(self, test_session, script, repo):
        report = await _make_report(test_session, script)
        deleted = await repo.delete_by_id(report.id)
        assert deleted is True

    async def test_delete_by_id_missing_returns_false(self, test_session, repo):
        deleted = await repo.delete_by_id(uuid.uuid4())
        assert deleted is False

    async def test_exists_true(self, test_session, script, repo):
        report = await _make_report(test_session, script)
        assert await repo.exists(report.id) is True

    async def test_exists_false(self, test_session, repo):
        assert await repo.exists(uuid.uuid4()) is False


# ──────────────────────────────────────────────────────────────────────────────
# Score fields validation
# ──────────────────────────────────────────────────────────────────────────────

class TestQualityReportScoreFields:
    async def test_all_score_fields_stored(self, test_session, script, repo):
        report = QualityReport(
            script_id=script.id,
            grammar_score=91.0,
            fact_consistency_score=87.5,
            engagement_score=83.0,
            retention_score=79.5,
            seo_score=88.0,
            uniqueness_score=72.0,
            readability_score=90.0,
            overall_score=84.4,
            passed=True,
            status=QualityStatus.PASSED,
        )
        created = await repo.create(report)
        fetched = await repo.get_by_id(created.id)
        assert fetched.grammar_score == 91.0
        assert fetched.fact_consistency_score == 87.5
        assert fetched.engagement_score == 83.0
        assert fetched.retention_score == 79.5
        assert fetched.seo_score == 88.0
        assert fetched.uniqueness_score == 72.0
        assert fetched.readability_score == 90.0
        assert fetched.overall_score == 84.4