from dataclasses import dataclass
from datetime import datetime

from google.oauth2.credentials import Credentials
from pydantic import SecretStr

CALENDAR_SCOPES = ("https://www.googleapis.com/auth/calendar",)


@dataclass(frozen=True, slots=True)
class GoogleOAuthTokens:
    access_token: SecretStr | None
    refresh_token: SecretStr | None
    token_uri: str
    client_id: str
    client_secret: SecretStr
    scopes: tuple[str, ...] = CALENDAR_SCOPES
    expiry: datetime | None = None

    def to_credentials(self) -> Credentials:
        return Credentials(
            token=self.access_token.get_secret_value() if self.access_token else None,
            refresh_token=(
                self.refresh_token.get_secret_value() if self.refresh_token else None
            ),
            token_uri=self.token_uri,
            client_id=self.client_id,
            client_secret=self.client_secret.get_secret_value(),
            scopes=list(self.scopes),
        )


@dataclass(frozen=True, slots=True)
class GoogleOAuthConnection:
    admin_telegram_id: int
    connected_at: datetime
