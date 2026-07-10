from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.diagnostics import DiagnosticsService
from app.integrations.google_calendar import GoogleCalendarAccessLostError
from app.settings.config import Settings


@pytest.mark.asyncio
async def test_diagnostics_report_uses_safe_configuration_flags() -> None:
    settings = Settings(
        telegram_bot_token="secret-token",
        telegram_admin_id="123",
        google_oauth_client_id="client-id",
        google_oauth_client_secret="client-secret",
        google_oauth_refresh_token="refresh-token",
        google_admin_email="admin@example.com",
    )

    report = await DiagnosticsService(settings).build_report()
    payload = report.as_dict()

    assert payload["status"] == "ok"
    rendered = str(payload)
    assert "secret-token" not in rendered
    assert "client-secret" not in rendered
    assert "refresh-token" not in rendered
    assert "admin@example.com" not in rendered
    assert "google_refresh_token_configured" in rendered


@pytest.mark.asyncio
async def test_diagnostics_warns_when_google_calendar_is_not_connected() -> None:
    settings = Settings(
        google_oauth_client_id="",
        google_oauth_client_secret="",
        google_oauth_refresh_token="",
    )

    report = await DiagnosticsService(settings).build_report()

    google_check = next(check for check in report.checks if check.name == "google_calendar")

    assert google_check.status == "warning"
    assert google_check.details["google_refresh_token_configured"] is False


@pytest.mark.asyncio
async def test_diagnostics_runs_runtime_connectivity_checks() -> None:
    settings = Settings(
        telegram_bot_token="secret-token",
        telegram_admin_id="123",
        google_oauth_client_id="client-id",
        google_oauth_client_secret="client-secret",
        google_oauth_refresh_token="refresh-token",
    )
    sessions = FakeSessionFactory()
    google = FakeGoogleCalendar()

    report = await DiagnosticsService(
        settings,
        session_factory=sessions,
        telegram_bot=FakeTelegramBot(),
        google_calendar=google,
        now=lambda: datetime(2026, 7, 10, 12, 0, tzinfo=UTC),
    ).build_report()

    assert report.status == "warning"
    telegram_check = next(check for check in report.checks if check.name == "telegram")
    database_check = next(check for check in report.checks if check.name == "database")
    google_check = next(check for check in report.checks if check.name == "google_calendar")
    worker_check = next(check for check in report.checks if check.name == "worker")

    assert telegram_check.details["telegram_api_reachable"] is True
    assert database_check.details["database_reachable"] is True
    assert google_check.details["google_calendar_reachable"] is True
    assert google.calls == 1
    assert worker_check.status == "warning"
    assert worker_check.details["pending_jobs"] == 2
    assert worker_check.details["failed_jobs"] == 1
    assert worker_check.details["due_jobs"] == 2
    assert worker_check.details["stale_running_jobs"] == 1


@pytest.mark.asyncio
async def test_diagnostics_reports_google_connectivity_error_safely() -> None:
    settings = Settings(
        telegram_bot_token="secret-token",
        telegram_admin_id="123",
        google_oauth_client_id="client-id",
        google_oauth_client_secret="client-secret",
        google_oauth_refresh_token="refresh-token",
    )

    report = await DiagnosticsService(
        settings,
        google_calendar=FailingGoogleCalendar(),
    ).build_report()

    google_check = next(check for check in report.checks if check.name == "google_calendar")

    assert google_check.status == "error"
    assert google_check.details["google_calendar_reachable"] is False
    assert google_check.details["error_code"] == "google_calendar_access_lost"
    rendered = str(report.as_dict())
    assert "secret-token" not in rendered
    assert "client-secret" not in rendered
    assert "refresh-token" not in rendered


class FakeTelegramBot:
    async def get_me(self):
        return SimpleNamespace(id=42)


class FakeGoogleCalendar:
    def __init__(self) -> None:
        self.calls = 0

    def list_busy_intervals(self, *, time_min, time_max) -> list:
        self.calls += 1
        assert time_max > time_min
        return []


class FailingGoogleCalendar:
    def list_busy_intervals(self, *, time_min, time_max) -> list:
        raise GoogleCalendarAccessLostError()


class FakeRows:
    def __init__(self, rows) -> None:
        self.rows = rows

    def all(self):
        return self.rows


class FakeSessionFactory:
    def __init__(self) -> None:
        self.execute_calls = 0
        self.scalar_values = [2, 1]

    def __call__(self):
        return FakeSession(self)


class FakeSession:
    def __init__(self, factory: FakeSessionFactory) -> None:
        self.factory = factory

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def execute(self, statement):
        self.factory.execute_calls += 1
        if self.factory.execute_calls == 1:
            return FakeRows([])
        return FakeRows([("pending", 2), ("failed", 1)])

    async def scalar(self, statement):
        return self.factory.scalar_values.pop(0)
