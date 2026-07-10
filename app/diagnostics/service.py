from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.settings.config import Settings

DiagnosticStatus = Literal["ok", "warning", "error"]


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
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def build_report(self) -> DiagnosticsReport:
        return DiagnosticsReport(
            checks=[
                self._telegram_check(),
                self._database_check(),
                self._google_calendar_check(),
                self._worker_check(),
            ]
        )

    def _telegram_check(self) -> DiagnosticCheck:
        configured = self.settings.telegram_bot_token is not None
        admin_configured = self.settings.telegram_admin_id is not None
        status: DiagnosticStatus = "ok" if configured and admin_configured else "error"
        return DiagnosticCheck(
            name="telegram",
            status=status,
            message=(
                "Telegram configuration is ready."
                if status == "ok"
                else "Telegram configuration is incomplete."
            ),
            details={
                "telegram_bot_token_configured": configured,
                "telegram_admin_id_configured": admin_configured,
            },
        )

    def _database_check(self) -> DiagnosticCheck:
        configured = bool(self.settings.database_url)
        return DiagnosticCheck(
            name="database",
            status="ok" if configured else "error",
            message="Database URL is configured." if configured else "Database URL is missing.",
            details={"database_configured": configured},
        )

    def _google_calendar_check(self) -> DiagnosticCheck:
        oauth_configured = bool(
            self.settings.google_oauth_client_id and self.settings.google_oauth_client_secret
        )
        refresh_configured = self.settings.google_oauth_refresh_token is not None
        status: DiagnosticStatus = "ok" if oauth_configured and refresh_configured else "warning"
        return DiagnosticCheck(
            name="google_calendar",
            status=status,
            message=(
                "Google Calendar configuration is ready."
                if status == "ok"
                else "Google Calendar configuration is incomplete."
            ),
            details={
                "google_oauth_configured": oauth_configured,
                "google_refresh_token_configured": refresh_configured,
                "google_calendar_id_configured": bool(self.settings.google_calendar_id),
                "google_admin_email_configured": self.settings.google_admin_email is not None,
            },
        )

    def _worker_check(self) -> DiagnosticCheck:
        return DiagnosticCheck(
            name="worker",
            status="ok",
            message="Worker settings are configured.",
            details={
                "worker_poll_interval_seconds": self.settings.worker_poll_interval_seconds,
                "integration_max_retries": self.settings.integration_max_retries,
                "audit_log_retention_days": self.settings.audit_log_retention_days,
            },
        )
