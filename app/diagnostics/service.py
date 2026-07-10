from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from sqlalchemy import func, select, text

from app.integrations.google_calendar.errors import (
    GoogleCalendarAccessLostError,
    GoogleCalendarError,
    GoogleCalendarNotConnectedError,
)
from app.logging.config import get_logger
from app.persistence.models.background_job import BackgroundJob
from app.persistence.models.enums import BackgroundJobStatus
from app.settings.config import Settings

DiagnosticStatus = Literal["ok", "warning", "error"]

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class DiagnosticCheck:
    name: str
    status: DiagnosticStatus
    message: str
    details: dict[str, bool | int | str | None]


@dataclass(frozen=True, slots=True)
class DiagnosticsReport:
    checks: list[DiagnosticCheck]

    @property
    def status(self) -> DiagnosticStatus:
        statuses = {check.status for check in self.checks}
        if "error" in statuses:
            return "error"
        if "warning" in statuses:
            return "warning"
        return "ok"

    def as_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "checks": [
                {
                    "name": check.name,
                    "status": check.status,
                    "message": check.message,
                    "details": check.details,
                }
                for check in self.checks
            ],
        }


class DiagnosticsService:
    def __init__(
        self,
        settings: Settings,
        *,
        session_factory: Callable[[], Any] | None = None,
        telegram_bot: Any | None = None,
        google_calendar: Any | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.settings = settings
        self.session_factory = session_factory
        self.telegram_bot = telegram_bot
        self.google_calendar = google_calendar
        self.now = now or (lambda: datetime.now(UTC))

    async def build_report(self) -> DiagnosticsReport:
        return DiagnosticsReport(
            checks=[
                await self._safe_check("telegram", self._telegram_check),
                await self._safe_check("database", self._database_check),
                await self._safe_check("google_calendar", self._google_calendar_check),
                await self._safe_check("worker", self._worker_check),
            ]
        )

    async def _telegram_check(self) -> DiagnosticCheck:
        configured = self.settings.telegram_bot_token is not None
        admin_configured = self.settings.telegram_admin_id is not None
        if not configured or not admin_configured:
            return DiagnosticCheck(
                name="telegram",
                status="error",
                message="Telegram configuration is incomplete.",
                details={
                    "telegram_bot_token_configured": configured,
                    "telegram_admin_id_configured": admin_configured,
                    "telegram_api_reachable": False,
                },
            )

        if self.telegram_bot is None:
            return DiagnosticCheck(
                name="telegram",
                status="ok",
                message="Telegram configuration is ready.",
                details={
                    "telegram_bot_token_configured": configured,
                    "telegram_admin_id_configured": admin_configured,
                    "telegram_api_reachable": None,
                },
            )

        bot_info = await self.telegram_bot.get_me()
        return DiagnosticCheck(
            name="telegram",
            status="ok",
            message="Telegram API is reachable.",
            details={
                "telegram_bot_token_configured": configured,
                "telegram_admin_id_configured": admin_configured,
                "telegram_api_reachable": True,
                "telegram_bot_id": getattr(bot_info, "id", None),
            },
        )

    async def _database_check(self) -> DiagnosticCheck:
        configured = bool(self.settings.database_url)
        if not configured:
            return DiagnosticCheck(
                name="database",
                status="error",
                message="Database URL is missing.",
                details={"database_configured": False, "database_reachable": False},
            )

        if self.session_factory is None:
            return DiagnosticCheck(
                name="database",
                status="ok",
                message="Database URL is configured.",
                details={"database_configured": True, "database_reachable": None},
            )

        async with self.session_factory() as session:
            await session.execute(text("SELECT 1"))
        return DiagnosticCheck(
            name="database",
            status="ok",
            message="Database connection is reachable.",
            details={"database_configured": True, "database_reachable": True},
        )

    async def _google_calendar_check(self) -> DiagnosticCheck:
        oauth_configured = bool(
            self.settings.google_oauth_client_id and self.settings.google_oauth_client_secret
        )
        refresh_configured = self.settings.google_oauth_refresh_token is not None
        base_details = {
            "google_oauth_configured": oauth_configured,
            "google_refresh_token_configured": refresh_configured,
            "google_calendar_id_configured": bool(self.settings.google_calendar_id),
            "google_admin_email_configured": self.settings.google_admin_email is not None,
        }
        if not oauth_configured or not refresh_configured:
            return DiagnosticCheck(
                name="google_calendar",
                status="warning",
                message="Google Calendar configuration is incomplete.",
                details={**base_details, "google_calendar_reachable": False},
            )

        if self.google_calendar is None:
            return DiagnosticCheck(
                name="google_calendar",
                status="ok",
                message="Google Calendar configuration is ready.",
                details={**base_details, "google_calendar_reachable": None},
            )

        try:
            now = self.now()
            self.google_calendar.list_busy_intervals(
                time_min=now,
                time_max=now + timedelta(minutes=1),
            )
        except GoogleCalendarNotConnectedError as error:
            return self._google_calendar_error_check(error, status="warning", details=base_details)
        except GoogleCalendarAccessLostError as error:
            return self._google_calendar_error_check(error, status="error", details=base_details)
        except GoogleCalendarError as error:
            return self._google_calendar_error_check(error, status="error", details=base_details)

        return DiagnosticCheck(
            name="google_calendar",
            status="ok",
            message="Google Calendar API is reachable.",
            details={**base_details, "google_calendar_reachable": True},
        )

    async def _worker_check(self) -> DiagnosticCheck:
        base_details = {
            "worker_poll_interval_seconds": self.settings.worker_poll_interval_seconds,
            "integration_max_retries": self.settings.integration_max_retries,
            "audit_log_retention_days": self.settings.audit_log_retention_days,
        }
        if self.session_factory is None:
            return DiagnosticCheck(
                name="worker",
                status="ok",
                message="Worker settings are configured.",
                details=base_details,
            )

        now = self.now()
        async with self.session_factory() as session:
            rows = await session.execute(
                select(BackgroundJob.status, func.count(BackgroundJob.id)).group_by(
                    BackgroundJob.status
                )
            )
            counts = {str(status): int(count) for status, count in rows.all()}
            due_jobs = await session.scalar(
                select(func.count(BackgroundJob.id)).where(
                    BackgroundJob.status == BackgroundJobStatus.PENDING.value,
                    BackgroundJob.run_at <= now,
                )
            )
            stale_running = await session.scalar(
                select(func.count(BackgroundJob.id)).where(
                    BackgroundJob.status == BackgroundJobStatus.RUNNING.value,
                    BackgroundJob.locked_until.is_not(None),
                    BackgroundJob.locked_until <= now,
                )
            )

        failed_jobs = counts.get(BackgroundJobStatus.FAILED.value, 0)
        stale_count = int(stale_running or 0)
        status: DiagnosticStatus = "ok"
        message = "Background jobs table is reachable."
        if stale_count:
            status = "warning"
            message = "Background jobs have stale running locks."
        elif failed_jobs:
            status = "warning"
            message = "Background jobs contain failed jobs."

        return DiagnosticCheck(
            name="worker",
            status=status,
            message=message,
            details={
                **base_details,
                "pending_jobs": counts.get(BackgroundJobStatus.PENDING.value, 0),
                "running_jobs": counts.get(BackgroundJobStatus.RUNNING.value, 0),
                "failed_jobs": failed_jobs,
                "due_jobs": int(due_jobs or 0),
                "stale_running_jobs": stale_count,
            },
        )

    async def _safe_check(
        self,
        name: str,
        check: Callable[[], Any],
    ) -> DiagnosticCheck:
        try:
            return await check()
        except Exception as error:
            logger.error(
                "Diagnostics check failed",
                extra={
                    "event": "diagnostics_check_failed",
                    "check": name,
                    "error_type": type(error).__name__,
                },
            )
            return DiagnosticCheck(
                name=name,
                status="error",
                message=f"{name} diagnostics check failed.",
                details={"error_type": type(error).__name__},
            )

    @staticmethod
    def _google_calendar_error_check(
        error: GoogleCalendarError,
        *,
        status: DiagnosticStatus,
        details: dict[str, bool | int | str | None],
    ) -> DiagnosticCheck:
        return DiagnosticCheck(
            name="google_calendar",
            status=status,
            message="Google Calendar API check failed.",
            details={
                **details,
                "google_calendar_reachable": False,
                "error_code": error.code,
                "error_type": type(error).__name__,
            },
        )
