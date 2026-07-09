from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.core.booking import BookingRecord, BookingStatus
from app.persistence.models.enums import BackgroundJobType
from app.settings.config import Settings
from app.worker.scheduler import BackgroundJobScheduler, BackgroundJobScheduleRequest

NOW = datetime(2026, 7, 10, 9, 0, tzinfo=UTC)


class FakeScheduleRepository:
    def __init__(self) -> None:
        self.requests: list[BackgroundJobScheduleRequest] = []
        self.pending_bookings: list[BookingRecord] = []
        self.confirmed_bookings: list[BookingRecord] = []

    async def enqueue_job(self, request: BackgroundJobScheduleRequest) -> uuid.UUID:
        self.requests.append(request)
        return uuid.uuid4()

    async def list_pending_bookings_for_ttl(self, *, now: datetime) -> list[BookingRecord]:
        return self.pending_bookings

    async def list_confirmed_bookings_for_reminders(
        self,
        *,
        now: datetime,
    ) -> list[BookingRecord]:
        return self.confirmed_bookings


def settings() -> Settings:
    return Settings(integration_max_retries=3, audit_log_retention_days=30)


def booking(
    *,
    status: BookingStatus = BookingStatus.PENDING,
    starts_at: datetime | None = None,
    reserved_until: datetime | None = None,
) -> BookingRecord:
    starts_at = starts_at or NOW + timedelta(days=3)
    return BookingRecord(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        meeting_type_id=uuid.uuid4(),
        duration_minutes=60,
        starts_at=starts_at,
        ends_at=starts_at + timedelta(hours=1),
        status=status,
        reserved_until=reserved_until,
    )


@pytest.mark.asyncio
async def test_scheduler_adds_ttl_job_for_pending_booking() -> None:
    repository = FakeScheduleRepository()
    scheduler = BackgroundJobScheduler(repository=repository, settings=settings())
    item = booking(reserved_until=NOW + timedelta(hours=48))

    await scheduler.schedule_booking_created(item, now=NOW)

    assert repository.requests == [
        BackgroundJobScheduleRequest(
            job_type=BackgroundJobType.BOOKING_TTL.value,
            run_at=NOW + timedelta(hours=48),
            booking_id=item.id,
            payload={"booking_id": str(item.id)},
            max_attempts=3,
        )
    ]


@pytest.mark.asyncio
async def test_scheduler_skips_ttl_for_confirmed_booking() -> None:
    repository = FakeScheduleRepository()
    scheduler = BackgroundJobScheduler(repository=repository, settings=settings())

    await scheduler.schedule_booking_created(
        booking(status=BookingStatus.CONFIRMED, reserved_until=NOW + timedelta(hours=48)),
        now=NOW,
    )

    assert repository.requests == []


@pytest.mark.asyncio
async def test_scheduler_adds_reminders_for_confirmed_booking() -> None:
    repository = FakeScheduleRepository()
    scheduler = BackgroundJobScheduler(repository=repository, settings=settings())
    item = booking(status=BookingStatus.CONFIRMED, starts_at=NOW + timedelta(days=3))

    await scheduler.schedule_booking_confirmed(item, now=NOW)

    scheduled = [
        (request.job_type, request.run_at, request.payload) for request in repository.requests
    ]
    assert scheduled == [
        (
            BackgroundJobType.TELEGRAM_REMINDER.value,
            item.starts_at - timedelta(hours=24),
            {
                "booking_id": str(item.id),
                "reminder_kind": "24h",
                "check_google_event": True,
            },
        ),
        (
            BackgroundJobType.TELEGRAM_REMINDER.value,
            item.starts_at - timedelta(hours=1),
            {
                "booking_id": str(item.id),
                "reminder_kind": "1h",
                "check_google_event": True,
            },
        ),
    ]


@pytest.mark.asyncio
async def test_scheduler_skips_past_reminders() -> None:
    repository = FakeScheduleRepository()
    scheduler = BackgroundJobScheduler(repository=repository, settings=settings())
    item = booking(status=BookingStatus.CONFIRMED, starts_at=NOW + timedelta(hours=2))

    await scheduler.schedule_booking_confirmed(item, now=NOW)

    assert len(repository.requests) == 1
    assert repository.requests[0].payload["reminder_kind"] == "1h"


@pytest.mark.asyncio
async def test_scheduler_adds_audit_cleanup_job() -> None:
    repository = FakeScheduleRepository()
    scheduler = BackgroundJobScheduler(repository=repository, settings=settings())

    await scheduler.schedule_audit_cleanup(now=NOW)

    assert repository.requests == [
        BackgroundJobScheduleRequest(
            job_type=BackgroundJobType.AUDIT_LOG_CLEANUP.value,
            run_at=NOW,
            payload={"retention_days": 30},
            max_attempts=3,
        )
    ]


@pytest.mark.asyncio
async def test_scheduler_recovers_jobs_after_restart() -> None:
    repository = FakeScheduleRepository()
    pending = booking(reserved_until=NOW + timedelta(hours=48))
    confirmed = booking(status=BookingStatus.CONFIRMED, starts_at=NOW + timedelta(days=3))
    repository.pending_bookings = [pending]
    repository.confirmed_bookings = [confirmed]
    scheduler = BackgroundJobScheduler(repository=repository, settings=settings())

    recovered = await scheduler.recover_jobs(now=NOW)

    assert recovered == 3
    assert [request.job_type for request in repository.requests] == [
        BackgroundJobType.BOOKING_TTL.value,
        BackgroundJobType.TELEGRAM_REMINDER.value,
        BackgroundJobType.TELEGRAM_REMINDER.value,
        BackgroundJobType.AUDIT_LOG_CLEANUP.value,
    ]
