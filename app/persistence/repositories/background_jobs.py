from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.persistence.models import AuditLog, BackgroundJob, Booking, SlotReservation, User
from app.persistence.models.enums import (
    AuditActorType,
    BackgroundJobStatus,
    BookingStatus,
)
from app.worker.jobs import BackgroundJobRecord, ReminderBooking


class SqlAlchemyBackgroundJobRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

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


def _job_record(job: BackgroundJob) -> BackgroundJobRecord:
    return BackgroundJobRecord(
        id=job.id,
        job_type=job.job_type,
        attempts=job.attempts,
        max_attempts=job.max_attempts,
        payload=dict(job.payload or {}),
        booking_id=job.booking_id,
    )
