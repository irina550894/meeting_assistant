from collections.abc import Callable
from datetime import datetime
from secrets import token_urlsafe

from google_auth_oauthlib.flow import Flow
from pydantic import SecretStr

from app.integrations.google_calendar.entities import CALENDAR_SCOPES, GoogleOAuthTokens
from app.integrations.google_calendar.errors import GoogleCalendarError
from app.integrations.google_calendar.token_store import GoogleOAuthTokenStore
from app.logging.config import get_logger
from app.settings.config import Settings

logger = get_logger(__name__)


class GoogleOAuthService:
    def __init__(
        self,
        *,
        settings: Settings,
        token_store: GoogleOAuthTokenStore,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.settings = settings
        self.token_store = token_store
        self.now = now or datetime.utcnow

    def authorization_url(self, *, admin_telegram_id: int) -> tuple[str, str]:
        flow = self._flow()
        state = token_urlsafe(24)
        url, _ = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent",
            state=state,
        )
        logger.info(
            "Google OAuth started",
            extra={"event": "google_oauth_started", "admin_id": admin_telegram_id},
        )
        return url, state

    async def handle_callback(self, *, code: str, admin_telegram_id: int) -> None:
        flow = self._flow()
        try:
            flow.fetch_token(code=code)
        except Exception as error:
            logger.warning(
                "Google OAuth failed",
                extra={
                    "event": "google_oauth_error",
                    "admin_id": admin_telegram_id,
                    "error_type": type(error).__name__,
                },
            )
            raise GoogleCalendarError("google_oauth_error", "Google OAuth failed.") from error

        credentials = flow.credentials
        tokens = GoogleOAuthTokens(
            access_token=SecretStr(credentials.token) if credentials.token else None,
            refresh_token=(
                SecretStr(credentials.refresh_token) if credentials.refresh_token else None
            ),
            token_uri=credentials.token_uri,
            client_id=self._client_id(),
            client_secret=self._client_secret(),
            scopes=tuple(credentials.scopes or CALENDAR_SCOPES),
            expiry=credentials.expiry,
        )
        await self.token_store.save(tokens)
        logger.info(
            "Google Calendar connected",
            extra={"event": "google_calendar_connected", "admin_id": admin_telegram_id},
        )

    def _flow(self) -> Flow:
        redirect_uri = self.settings.google_oauth_redirect_uri
        if not redirect_uri:
            raise GoogleCalendarError(
                "google_oauth_not_configured",
                "GOOGLE_OAUTH_REDIRECT_URI is required.",
            )
        return Flow.from_client_config(
            self._client_config(),
            scopes=list(CALENDAR_SCOPES),
            redirect_uri=redirect_uri,
        )

    def _client_config(self) -> dict[str, dict[str, object]]:
        return {
            "web": {
                "client_id": self._client_id(),
                "client_secret": self._client_secret().get_secret_value(),
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [self.settings.google_oauth_redirect_uri],
            }
        }

    def _client_id(self) -> str:
        if not self.settings.google_oauth_client_id:
            raise GoogleCalendarError(
                "google_oauth_not_configured",
                "GOOGLE_OAUTH_CLIENT_ID is required.",
            )
        return self.settings.google_oauth_client_id

    def _client_secret(self) -> SecretStr:
        if not self.settings.google_oauth_client_secret:
            raise GoogleCalendarError(
                "google_oauth_not_configured",
                "GOOGLE_OAUTH_CLIENT_SECRET is required.",
            )
        return self.settings.google_oauth_client_secret
