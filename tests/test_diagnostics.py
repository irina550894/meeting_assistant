import pytest

from app.diagnostics import DiagnosticsService
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
