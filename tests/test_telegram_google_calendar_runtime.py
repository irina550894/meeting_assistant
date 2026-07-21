from pydantic import SecretStr

from app.integrations.google_calendar import GoogleOAuthTokens
from app.integrations.telegram import runtime
from app.settings.config import Settings


async def test_telegram_google_calendar_runtime_prefers_stored_oauth_tokens(monkeypatch) -> None:
    stored_tokens = GoogleOAuthTokens(
        access_token=SecretStr("stored-access-token"),
        refresh_token=SecretStr("stored-refresh-token"),
        token_uri="https://oauth2.googleapis.com/token",
        client_id="client-id",
        client_secret=SecretStr("client-secret"),
    )

    class FakeGoogleOAuthTokenStore:
        def __init__(self, *, session_factory, settings):
            self.session_factory = session_factory
            self.settings = settings

        async def get(self):
            return stored_tokens

    monkeypatch.setattr(runtime, "SqlAlchemyGoogleOAuthTokenStore", FakeGoogleOAuthTokenStore)

    client = await runtime._google_calendar_runtime(
        Settings(
            google_oauth_client_id="client-id",
            google_oauth_client_secret="client-secret",
            google_oauth_refresh_token="env-refresh-token",
        )
    )

    assert client is not None
    assert client.token_provider().refresh_token is not None
    assert client.token_provider().refresh_token.get_secret_value() == "stored-refresh-token"


async def test_telegram_google_calendar_runtime_falls_back_to_env_refresh_token(monkeypatch) -> None:
    class FakeGoogleOAuthTokenStore:
        def __init__(self, *, session_factory, settings):
            self.session_factory = session_factory
            self.settings = settings

        async def get(self):
            return None

    monkeypatch.setattr(runtime, "SqlAlchemyGoogleOAuthTokenStore", FakeGoogleOAuthTokenStore)

    client = await runtime._google_calendar_runtime(
        Settings(
            google_oauth_client_id="client-id",
            google_oauth_client_secret="client-secret",
            google_oauth_refresh_token="env-refresh-token",
        )
    )

    assert client is not None
    assert client.token_provider().refresh_token is not None
    assert client.token_provider().refresh_token.get_secret_value() == "env-refresh-token"
