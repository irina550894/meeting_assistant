from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from app.persistence.models.enums import BackgroundJobType
from app.settings.config import Settings
from app.worker.jobs import (
    BackgroundJobRecord,
    JobTemporaryError,
    ReminderBooking,
    WorkerService,
)

NOW = datetime(2026, 7, 10, 9, 0, tzinfo=UTC)


class FakeJobRepository:
    def __init__(self, job: BackgroundJobRecord | None = None) -> None:
        self.job = job
        self.expired_bookings: list[uuid.UUID] = []
        self.succeeded: list[uuid.UUID] = []
        self.failed: list[tuple[uuid.UUID, str]] = []
        self.retries: list[tuple[uuid.UUID, datetime, str]] = []
        self.cleanup_before: datetime | None = None
        self.reminder_booking: ReminderBooking | None = None

    async def claim_due_job(
        self,
        *,
        now: datetime,
        locked_until: datetime,
    ) -> BackgroundJobRecord | None:
        return self.job

    async def mark_succeeded(self, job_id: uuid.UUID, *, now: datetime) -> None:
        self.succeeded.append(job_id)

    async def mark_failed(self, job_id: uuid.UUID, *, now: datetime, error: str) -> None:
        self.failed.append((job_id, error))

    async def schedule_retry(
        self,
        job_id: uuid.UUID,
        *,
        run_at: datetime,
        locked_until: datetime | None,
        error: str,
    ) -> None:
        self.retries.append((job_id, run_at, error))

    async def expire_pending_booking(
        self,
        booking_id: uuid.UUID,
        *,
        now: datetime,
    ) -> bool:
        self.expired_bookings.append(booking_id)
        return True

    async def get_reminder_booking(self, booking_id: uuid.UUID) -> ReminderBooking | None:
        return self.reminder_booking

    async def cleanup_audit_logs(self, *, before: datetime) -> int:
        self.cleanup_before = before
        return 3


class FakeReminderSender:
    def __init__(self) -> None:
        self.sent: list[tuple[uuid.UUID, str]] = []

    async def send_reminder(self, booking: ReminderBooking, *, reminder_kind: str) -> None:
        self.sent.append((booking.booking_id, reminder_kind))


class FakeGoogleEventChecker:
    def __init__(self) -> None:
        self.checked: list[uuid.UUID] = []

    async def ensure_event_exists(self, booking: ReminderBooking) -> None:
        self.checked.append(booking.booking_id)


class FailingReminderSender:
    async def send_reminder(self, booking: ReminderBooking, *, reminder_kind: str) -> None:
        raise JobTemporaryError("telegram temporary error")


def settings() -> Settings:
    return Settings(worker_poll_interval_seconds=30, audit_log_retention_days=30)


def job(job_type: BackgroundJobType, **kwargs) -> BackgroundJobRecord:
    return BackgroundJobRecord(
        id=kwargs.get("job_id", uuid.uuid4()),
        job_type=job_type.value,
        attempts=kwargs.get("attempts", 1),
        max_attempts=kwargs.get("max_attempts", 3),
        payload=kwargs.get("payload", {}),
        booking_id=kwargs.get("booking_id"),
    )


@pytest.mark.asyncio
async def test_worker_returns_empty_result_without_due_jobs() -> None:
    repository = FakeJobRepository()
    service = WorkerService(repository=repository, settings=settings(), now=lambda: NOW)

    result = await service.run_once()

    assert result.claimed is False


@pytest.mark.asyncio
async def test_worker_expires_pending_booking_by_ttl() -> None:
    booking_id = uuid.uuid4()
    repository = FakeJobRepository(job(BackgroundJobType.BOOKING_TTL, booking_id=booking_id))
    service = WorkerService(repository=repository, settings=settings(), now=lambda: NOW)

    result = await service.run_once()

    assert result.status == "succeeded"
    assert repository.expired_bookings == [booking_id]
    assert repository.succeeded == [repository.job.id]


@pytest.mark.asyncio
async def test_worker_checks_google_event_before_reminder() -> None:
    booking_id = uuid.uuid4()
    repository = FakeJobRepository(
        job(
            BackgroundJobType.TELEGRAM_REMINDER,
            booking_id=booking_id,
            payload={"reminder_kind": "1h", "check_google_event": True},
        )
    )
    repository.reminder_booking = ReminderBooking(
        booking_id=booking_id,
        user_telegram_id=123,
        starts_at=NOW,
        meeting_url="https://example.test/meeting",
        google_calendar_event_id="event-1",
    )
    sender = FakeReminderSender()
    checker = FakeGoogleEventChecker()
    service = WorkerService(
        repository=repository,
        settings=settings(),
        reminder_sender=sender,
        google_event_checker=checker,
        now=lambda: NOW,
    )

    result = await service.run_once()

    assert result.status == "succeeded"
    assert checker.checked == [booking_id]
    assert sender.sent == [(booking_id, "1h")]


@pytest.mark.asyncio
async def test_worker_schedules_retry_for_temporary_error() -> None:
    booking_id = uuid.uuid4()
    repository = FakeJobRepository(
        job(BackgroundJobType.TELEGRAM_REMINDER, booking_id=booking_id, attempts=1)
    )
    repository.reminder_booking = ReminderBooking(
        booking_id=booking_id,
        user_telegram_id=123,
        starts_at=NOW,
        meeting_url=None,
        google_calendar_event_id=None,
    )
    service = WorkerService(
        repository=repository,
        settings=settings(),
        reminder_sender=FailingReminderSender(),
        now=lambda: NOW,
    )

    result = await service.run_once()

    assert result.status == "retry"
    assert repository.retries == [
        (repository.job.id, NOW.replace(minute=1), "telegram temporary error")
    ]


@pytest.mark.asyncio
async def test_worker_fails_job_after_max_attempts() -> None:
    booking_id = uuid.uuid4()
    repository = FakeJobRepository(
        job(BackgroundJobType.TELEGRAM_REMINDER, booking_id=booking_id, attempts=3, max_attempts=3)
    )
    repository.reminder_booking = ReminderBooking(
        booking_id=booking_id,
        user_telegram_id=123,
        starts_at=NOW,
        meeting_url=None,
        google_calendar_event_id=None,
    )
    service = WorkerService(
        repository=repository,
        settings=settings(),
        reminder_sender=FailingReminderSender(),
        now=lambda: NOW,
    )

    result = await service.run_once()

    assert result.status == "failed"
    assert repository.failed == [(repository.job.id, "telegram temporary error")]


@pytest.mark.asyncio
async def test_worker_cleans_old_audit_logs() -> None:
    repository = FakeJobRepository(job(BackgroundJobType.AUDIT_LOG_CLEANUP))
    service = WorkerService(repository=repository, settings=settings(), now=lambda: NOW)

    result = await service.run_once()

    assert result.status == "succeeded"
    assert repository.cleanup_before == datetime(2026, 6, 10, 9, 0, tzinfo=UTC)
