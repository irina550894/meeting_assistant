from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.sources import ActionSource
from app.core.booking import BookingRecord
from app.core.booking import BookingStatus as CoreBookingStatus
from app.persistence.models import AuditLog, BackgroundJob, Booking, SlotReservation, User
from app.persistence.models.enums import (
    AuditActorType,
    BackgroundJobStatus,
    BookingStatus,
)
from app.settings.config import Settings
from app.worker.jobs import BackgroundJobRecord, ReminderBooking
from app.worker.scheduler import BackgroundJobScheduler, BackgroundJobScheduleRequest


class CommittedBackgroundJobScheduler:
    def __init__(self, *, session_factory, settings: Settings) -> None:
        self.session_factory = session_factory
        self.settings = settings

    async def schedule_booking_created(
        self,
        booking: BookingRecord,
        *,
        now: datetime,
    ) -> None:
        async with self.session_factory() as session:
            async with session.begin():
                scheduler = BackgroundJobScheduler(
                    repository=SqlAlchemyBackgroundJobRepository(session),
                    settings=self.settings,
                )
                await scheduler.schedule_booking_created(booking, now=now)

    async def schedule_booking_confirmed(
        self,
        booking: BookingRecord,
        *,
        now: datetime,
    ) -> None:
        async with self.session_factory() as session:
            async with session.begin():
                scheduler = BackgroundJobScheduler(
                    repository=SqlAlchemyBackgroundJobRepository(session),
                    settings=self.settings,
                )
                await scheduler.schedule_booking_confirmed(booking, now=now)


class SqlAlchemyBackgroundJobRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def enqueue_job(self, request: BackgroundJobScheduleRequest) -> uuid.UUID:
        existing = (
            await self.session.scalars(
                select(BackgroundJob).where(
                    BackgroundJob.job_type == request.job_type,
                    BackgroundJob.booking_id == request.booking_id,
                    BackgroundJob.payload == request.payload,
                    BackgroundJob.status.in_(
                        [
                            BackgroundJobStatus.PENDING.value,
                            BackgroundJobStatus.RUNNING.value,
                        ]
                    ),
                )
            )
        ).first()
        if existing is not None:
            return existing.id

        job = BackgroundJob(
            job_type=request.job_type,
            status=BackgroundJobStatus.PENDING.value,
            run_at=request.run_at,
            max_attempts=request.max_attempts,
            payload=request.payload,
            booking_id=request.booking_id,
        )
        self.session.add(job)
        await self.session.flush()
        return job.id

    async def claim_due_job(
        self,
        *,
        now: datetime,
        locked_until: datetime,
    ) -> BackgroundJobRecord | None:
        statement = (
            select(BackgroundJob)
            .where(
                BackgroundJob.run_at <= now,
                or_(
                    BackgroundJob.status == BackgroundJobStatus.PENDING.value,
                    (
                        (BackgroundJob.status == BackgroundJobStatus.RUNNING.value)
                        & (BackgroundJob.locked_until <= now)
                    ),
                ),
            )
            .order_by(BackgroundJob.run_at, BackgroundJob.created_at)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        job = (await self.session.scalars(statement)).first()
        if job is None:
            return None

        job.status = BackgroundJobStatus.RUNNING.value
        job.locked_until = locked_until
        job.attempts += 1
        job.last_error = None
        await self.session.flush()
        return _job_record(job)

    async def mark_succeeded(self, job_id: uuid.UUID, *, now: datetime) -> None:
        job = await self.session.get(BackgroundJob, job_id)
        if job is None:
            return
        job.status = BackgroundJobStatus.SUCCEEDED.value
        job.locked_until = None
        job.last_error = None
        job.updated_at = now
        await self.session.flush()

    async def mark_failed(self, job_id: uuid.UUID, *, now: datetime, error: str) -> None:
        job = await self.session.get(BackgroundJob, job_id)
        if job is None:
            return
        job.status = BackgroundJobStatus.FAILED.value
        job.locked_until = None
        job.last_error = error[:2000]
        job.updated_at = now
        await self.session.flush()

    async def schedule_retry(
        self,
        job_id: uuid.UUID,
        *,
        run_at: datetime,
        locked_until: datetime | None,
        error: str,
    ) -> None:
        job = await self.session.get(BackgroundJob, job_id)
        if job is None:
            return
        job.status = BackgroundJobStatus.PENDING.value
        job.run_at = run_at
        job.locked_until = locked_until
        job.last_error = error[:2000]
        await self.session.flush()

    async def expire_pending_booking(
        self,
        booking_id: uuid.UUID,
        *,
        now: datetime,
    ) -> bool:
        booking = await self.session.get(Booking, booking_id)
        if booking is None or booking.status != BookingStatus.PENDING.value:
            return False

        booking.status = BookingStatus.EXPIRED.value
        booking.updated_at = now

        reservation = (
            await self.session.scalars(
                select(SlotReservation).where(SlotReservation.booking_id == booking_id)
            )
        ).first()
        if reservation is not None and reservation.released_at is None:
            reservation.released_at = now

        self.session.add(
            AuditLog(
                actor_type=AuditActorType.SYSTEM.value,
                action="booking_expired_by_ttl",
                source=ActionSource.WORKER.value,
                entity_type="booking",
                entity_id=booking_id,
                payload={},
                created_at=now,
            )
        )
        await self.session.flush()
        return True

    async def get_reminder_booking(self, booking_id: uuid.UUID) -> ReminderBooking | None:
        statement = (
            select(Booking, User)
            .join(User, Booking.user_id == User.id)
            .where(
                Booking.id == booking_id,
                Booking.status == BookingStatus.CONFIRMED.value,
            )
        )
        row = (await self.session.execute(statement)).first()
        if row is None:
            return None
        booking, user = row
        return ReminderBooking(
            booking_id=booking.id,
            user_telegram_id=user.telegram_id,
            starts_at=booking.starts_at,
            meeting_url=booking.meeting_url,
            google_calendar_event_id=booking.google_calendar_event_id,
        )

    async def cleanup_audit_logs(self, *, before: datetime) -> int:
        result = await self.session.execute(delete(AuditLog).where(AuditLog.created_at < before))
        await self.session.flush()
        return int(result.rowcount or 0)

    async def list_pending_bookings_for_ttl(self, *, now: datetime) -> list[BookingRecord]:
        bookings = await self.session.scalars(
            select(Booking).where(
                Booking.status == BookingStatus.PENDING.value,
                Booking.reserved_until.is_not(None),
            )
        )
        return [_booking_record(booking) for booking in bookings]

    async def list_confirmed_bookings_for_reminders(self, *, now: datetime) -> list[BookingRecord]:
        bookings = await self.session.scalars(
            select(Booking).where(
                Booking.status == BookingStatus.CONFIRMED.value,
                Booking.starts_at > now,
            )
        )
        return [_booking_record(booking) for booking in bookings]


def _job_record(job: BackgroundJob) -> BackgroundJobRecord:
    return BackgroundJobRecord(
        id=job.id,
        job_type=job.job_type,
        attempts=job.attempts,
        max_attempts=job.max_attempts,
        payload=dict(job.payload or {}),
        booking_id=job.booking_id,
    )


def _booking_record(booking: Booking) -> BookingRecord:
    return BookingRecord(
        id=booking.id,
        user_id=booking.user_id,
        meeting_type_id=booking.meeting_type_id,
        duration_minutes=booking.duration_minutes,
        starts_at=booking.starts_at,
        ends_at=booking.ends_at,
        status=CoreBookingStatus(booking.status),
        created_source=booking.created_source,
        user_comment=booking.user_comment,
        rejection_reason=booking.rejection_reason,
        cancellation_reason=booking.cancellation_reason,
        reserved_until=booking.reserved_until,
        google_calendar_event_id=booking.google_calendar_event_id,
        meeting_url=booking.meeting_url,
        is_reschedule_request=booking.is_reschedule_request,
        previous_booking_id=booking.previous_booking_id,
        created_at=booking.created_at,
        updated_at=booking.updated_at,
    )
