from datetime import datetime

import pytest
from pydantic import SecretStr

from app.integrations.google_calendar import GoogleCalendarAccessLostError, GoogleOAuthTokens
from app.interfaces.http.routes import google_oauth
from app.settings.config import Settings


@pytest.mark.asyncio
async def test_google_oauth_status_reports_connected(monkeypatch) -> None:
    tokens = _tokens()

    class FakeTokenStore:
        def __init__(self, **_: object) -> None:
            pass

        async def get(self) -> GoogleOAuthTokens:
            return tokens

    class FakeGoogleCalendarClient:
        def __init__(self, *, settings: Settings, token_provider: object) -> None:
            self.settings = settings
            self.token_provider = token_provider

        def list_busy_intervals(self, *, time_min: datetime, time_max: datetime) -> list[object]:
            assert time_max > time_min
            return []

    monkeypatch.setattr(google_oauth, "get_settings", _settings)
    monkeypatch.setattr(google_oauth, "SqlAlchemyGoogleOAuthTokenStore", FakeTokenStore)
    monkeypatch.setattr(google_oauth, "GoogleCalendarClient", FakeGoogleCalendarClient)

    assert await google_oauth.google_oauth_status() == {
        "connected": True,
        "needs_reconnect": False,
        "error_code": None,
    }


@pytest.mark.asyncio
async def test_google_oauth_status_reports_reconnect_needed(monkeypatch) -> None:
    tokens = _tokens()

    class FakeTokenStore:
        def __init__(self, **_: object) -> None:
            pass

        async def get(self) -> GoogleOAuthTokens:
            return tokens

    class FakeGoogleCalendarClient:
        def __init__(self, *, settings: Settings, token_provider: object) -> None:
            self.settings = settings
            self.token_provider = token_provider

        def list_busy_intervals(self, *, time_min: datetime, time_max: datetime) -> list[object]:
            raise GoogleCalendarAccessLostError()

    monkeypatch.setattr(google_oauth, "get_settings", _settings)
    monkeypatch.setattr(google_oauth, "SqlAlchemyGoogleOAuthTokenStore", FakeTokenStore)
    monkeypatch.setattr(google_oauth, "GoogleCalendarClient", FakeGoogleCalendarClient)

    assert await google_oauth.google_oauth_status() == {
        "connected": False,
        "needs_reconnect": True,
        "error_code": "google_calendar_access_lost",
    }


def _settings() -> Settings:
    return Settings(
        google_oauth_client_id="client-id",
        google_oauth_client_secret=SecretStr("client-secret"),
        google_oauth_redirect_uri="https://calendar.example.com/oauth/google/callback",
        google_calendar_id="primary",
    )


def _tokens() -> GoogleOAuthTokens:
    return GoogleOAuthTokens(
        access_token=SecretStr("access-token"),
        refresh_token=SecretStr("refresh-token"),
        token_uri="https://oauth2.googleapis.com/token",
        client_id="client-id",
        client_secret=SecretStr("client-secret"),
    )
