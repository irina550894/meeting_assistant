from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol

from app.logging.config import get_logger
from app.persistence.models.enums import BackgroundJobType
from app.settings.config import Settings

logger = get_logger(__name__)


class JobTemporaryError(RuntimeError):
    """Error type for retryable worker failures."""


class JobPermanentError(RuntimeError):
    """Error type for non-retryable worker failures."""


@dataclass(frozen=True, slots=True)
class BackgroundJobRecord:
    id: uuid.UUID
    job_type: str
    attempts: int
    max_attempts: int
    payload: dict
    booking_id: uuid.UUID | None = None


@dataclass(frozen=True, slots=True)
class ReminderBooking:
    booking_id: uuid.UUID
    user_telegram_id: int
    starts_at: datetime
    meeting_url: str | None
    google_calendar_event_id: str | None


@dataclass(frozen=True, slots=True)
class WorkerRunResult:
    claimed: bool
    job_type: str | None = None
    status: str | None = None


class BackgroundJobRepository(Protocol):
    async def claim_due_job(
        self,
        *,
        now: datetime,
        locked_until: datetime,
    ) -> BackgroundJobRecord | None: ...

    async def mark_succeeded(self, job_id: uuid.UUID, *, now: datetime) -> None: ...

    async def mark_failed(self, job_id: uuid.UUID, *, now: datetime, error: str) -> None: ...

    async def schedule_retry(
        self,
        job_id: uuid.UUID,
        *,
        run_at: datetime,
        locked_until: datetime | None,
        error: str,
    ) -> None: ...

    async def expire_pending_booking(
        self,
        booking_id: uuid.UUID,
        *,
        now: datetime,
    ) -> bool: ...

    async def get_reminder_booking(self, booking_id: uuid.UUID) -> ReminderBooking | None: ...

    async def cleanup_audit_logs(self, *, before: datetime) -> int: ...


class ReminderSender(Protocol):
    async def send_reminder(self, booking: ReminderBooking, *, reminder_kind: str) -> None: ...


class GoogleEventChecker(Protocol):
    async def ensure_event_exists(self, booking: ReminderBooking) -> None: ...


class IntegrationRetryHandler(Protocol):
    async def retry(self, payload: dict) -> None: ...


class NoopReminderSender:
    async def send_reminder(self, booking: ReminderBooking, *, reminder_kind: str) -> None:
        logger.info(
            "Reminder sender is not configured",
            extra={
                "event": "reminder_sender_not_configured",
                "booking_id": str(booking.booking_id),
                "reminder_kind": reminder_kind,
            },
        )


class NoopGoogleEventChecker:
    async def ensure_event_exists(self, booking: ReminderBooking) -> None:
        logger.info(
            "Google event checker is not configured",
            extra={
                "event": "google_event_checker_not_configured",
                "booking_id": str(booking.booking_id),
            },
        )


class NoopIntegrationRetryHandler:
    async def retry(self, payload: dict) -> None:
        logger.info(
            "Integration retry handler is not configured",
            extra={"event": "integration_retry_handler_not_configured"},
        )


class WorkerService:
    def __init__(
        self,
        *,
        repository: BackgroundJobRepository,
        settings: Settings,
        reminder_sender: ReminderSender | None = None,
        google_event_checker: GoogleEventChecker | None = None,
        integration_retry_handler: IntegrationRetryHandler | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.repository = repository
        self.settings = settings
        self.reminder_sender = reminder_sender or NoopReminderSender()
        self.google_event_checker = google_event_checker or NoopGoogleEventChecker()
        self.integration_retry_handler = integration_retry_handler or NoopIntegrationRetryHandler()
        self.now = now or (lambda: datetime.now(UTC))

    async def run_once(self) -> WorkerRunResult:
        now = self.now()
        job = await self.repository.claim_due_job(
            now=now,
            locked_until=now + timedelta(seconds=self.settings.worker_poll_interval_seconds),
        )
        if job is None:
            logger.debug("Worker tick completed", extra={"event": "worker_tick", "jobs": 0})
            return WorkerRunResult(claimed=False)

        logger.info(
            "Background job started",
            extra={
                "event": "job_started",
                "job_id": str(job.id),
                "job_type": job.job_type,
                "attempt": job.attempts,
            },
        )
        try:
            await self._handle_job(job, now=now)
        except JobPermanentError as error:
            await self.repository.mark_failed(job.id, now=self.now(), error=str(error))
            logger.warning(
                "Background job failed",
                extra={"event": "job_failed", "job_id": str(job.id), "job_type": job.job_type},
            )
            return WorkerRunResult(claimed=True, job_type=job.job_type, status="failed")
        except Exception as error:
            if job.attempts >= job.max_attempts:
                await self.repository.mark_failed(job.id, now=self.now(), error=str(error))
                logger.warning(
                    "Background job exhausted retries",
                    extra={
                        "event": "job_failed",
                        "job_id": str(job.id),
                        "job_type": job.job_type,
                    },
                )
                return WorkerRunResult(claimed=True, job_type=job.job_type, status="failed")

            retry_at = self._retry_at(job)
            await self.repository.schedule_retry(
                job.id,
                run_at=retry_at,
                locked_until=None,
                error=str(error),
            )
            logger.warning(
                "Background job scheduled for retry",
                extra={
                    "event": "job_retry_scheduled",
                    "job_id": str(job.id),
                    "job_type": job.job_type,
                    "retry_at": retry_at.isoformat(),
                    "attempt": job.attempts,
                },
            )
            return WorkerRunResult(claimed=True, job_type=job.job_type, status="retry")

        await self.repository.mark_succeeded(job.id, now=self.now())
        logger.info(
            "Background job completed",
            extra={"event": "job_succeeded", "job_id": str(job.id), "job_type": job.job_type},
        )
        return WorkerRunResult(claimed=True, job_type=job.job_type, status="succeeded")

    async def _handle_job(self, job: BackgroundJobRecord, *, now: datetime) -> None:
        if job.job_type == BackgroundJobType.BOOKING_TTL:
            await self._expire_booking(job, now=now)
        elif job.job_type == BackgroundJobType.TELEGRAM_REMINDER:
            await self._send_reminder(job)
        elif job.job_type == BackgroundJobType.GOOGLE_EVENT_CHECK:
            await self._check_google_event(job)
        elif job.job_type == BackgroundJobType.INTEGRATION_RETRY:
            await self.integration_retry_handler.retry(job.payload)
        elif job.job_type == BackgroundJobType.AUDIT_LOG_CLEANUP:
            await self._cleanup_audit_logs(now=now)
        else:
            raise JobPermanentError(f"Unsupported background job type: {job.job_type}")

    async def _expire_booking(self, job: BackgroundJobRecord, *, now: datetime) -> None:
        booking_id = self._booking_id(job)
        expired = await self.repository.expire_pending_booking(booking_id, now=now)
        logger.info(
            "TTL job processed booking",
            extra={
                "event": "booking_ttl_processed",
                "booking_id": str(booking_id),
                "expired": expired,
            },
        )

    async def _send_reminder(self, job: BackgroundJobRecord) -> None:
        booking = await self._reminder_booking(job)
        if job.payload.get("check_google_event", True):
            await self.google_event_checker.ensure_event_exists(booking)
        reminder_kind = str(job.payload.get("reminder_kind", "default"))
        await self.reminder_sender.send_reminder(booking, reminder_kind=reminder_kind)

    async def _check_google_event(self, job: BackgroundJobRecord) -> None:
        booking = await self._reminder_booking(job)
        await self.google_event_checker.ensure_event_exists(booking)

    async def _cleanup_audit_logs(self, *, now: datetime) -> None:
        before = now - timedelta(days=self.settings.audit_log_retention_days)
        deleted = await self.repository.cleanup_audit_logs(before=before)
        logger.info(
            "Audit-log cleanup completed",
            extra={"event": "audit_log_cleanup_completed", "deleted": deleted},
        )

    async def _reminder_booking(self, job: BackgroundJobRecord) -> ReminderBooking:
        booking_id = self._booking_id(job)
        booking = await self.repository.get_reminder_booking(booking_id)
        if booking is None:
            raise JobPermanentError(f"Booking is not available for reminder: {booking_id}")
        return booking

    def _booking_id(self, job: BackgroundJobRecord) -> uuid.UUID:
        raw = job.booking_id or job.payload.get("booking_id")
        if raw is None:
            raise JobPermanentError("booking_id is required")
        return raw if isinstance(raw, uuid.UUID) else uuid.UUID(str(raw))

    def _retry_at(self, job: BackgroundJobRecord) -> datetime:
        delay_seconds = min(60 * (2 ** max(job.attempts - 1, 0)), 900)
        return self.now() + timedelta(seconds=delay_seconds)
