from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol

from app.core.booking import BookingRecord, BookingStatus
from app.persistence.models.enums import BackgroundJobType
from app.settings.config import Settings


@dataclass(frozen=True, slots=True)
class BackgroundJobScheduleRequest:
    job_type: str
    run_at: datetime
    payload: dict
    booking_id: uuid.UUID | None = None
    max_attempts: int = 3


class BackgroundJobSchedulerRepository(Protocol):
    async def enqueue_job(self, request: BackgroundJobScheduleRequest) -> uuid.UUID: ...

    async def list_pending_bookings_for_ttl(self, *, now: datetime) -> list[BookingRecord]: ...

    async def list_confirmed_bookings_for_reminders(
        self,
        *,
        now: datetime,
    ) -> list[BookingRecord]: ...


class BackgroundJobScheduler:
    def __init__(self, *, repository: BackgroundJobSchedulerRepository, settings: Settings) -> None:
        self.repository = repository
        self.settings = settings

    async def schedule_booking_created(self, booking: BookingRecord, *, now: datetime) -> None:
        if booking.status != BookingStatus.PENDING or booking.reserved_until is None:
            return
        await self.repository.enqueue_job(
            BackgroundJobScheduleRequest(
                job_type=BackgroundJobType.BOOKING_TTL.value,
                run_at=booking.reserved_until,
                booking_id=booking.id,
                payload={"booking_id": str(booking.id)},
                max_attempts=self.settings.integration_max_retries,
            )
        )

    async def schedule_booking_confirmed(self, booking: BookingRecord, *, now: datetime) -> None:
        if booking.status != BookingStatus.CONFIRMED:
            return
        for reminder_kind, delta in (("24h", timedelta(hours=24)), ("1h", timedelta(hours=1))):
            run_at = booking.starts_at - delta
            if run_at <= now:
                continue
            await self.repository.enqueue_job(
                BackgroundJobScheduleRequest(
                    job_type=BackgroundJobType.TELEGRAM_REMINDER.value,
                    run_at=run_at,
                    booking_id=booking.id,
                    payload={
                        "booking_id": str(booking.id),
                        "reminder_kind": reminder_kind,
                        "check_google_event": True,
                    },
                    max_attempts=self.settings.integration_max_retries,
                )
            )

    async def schedule_audit_cleanup(self, *, now: datetime) -> uuid.UUID:
        return await self.repository.enqueue_job(
            BackgroundJobScheduleRequest(
                job_type=BackgroundJobType.AUDIT_LOG_CLEANUP.value,
                run_at=now,
                payload={"retention_days": self.settings.audit_log_retention_days},
                max_attempts=self.settings.integration_max_retries,
            )
        )

    async def recover_jobs(self, *, now: datetime) -> int:
        scheduled = 0
        for booking in await self.repository.list_pending_bookings_for_ttl(now=now):
            before = scheduled
            await self.schedule_booking_created(booking, now=now)
            scheduled = before + 1

        for booking in await self.repository.list_confirmed_bookings_for_reminders(now=now):
            before = scheduled
            await self.schedule_booking_confirmed(booking, now=now)
            scheduled = before + 1

        await self.schedule_audit_cleanup(now=now)
        return scheduled + 1
