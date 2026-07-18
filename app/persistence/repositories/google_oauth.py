from datetime import UTC, datetime

from pydantic import SecretStr
from sqlalchemy import select

from app.integrations.google_calendar.entities import GoogleOAuthTokens
from app.persistence.models.oauth import GoogleOAuthToken
from app.settings.config import Settings


class SqlAlchemyGoogleOAuthTokenStore:
    def __init__(self, *, session_factory, settings: Settings) -> None:
        self.session_factory = session_factory
        self.settings = settings

    async def get(self) -> GoogleOAuthTokens | None:
        async with self.session_factory() as session:
            row = await session.scalar(
                select(GoogleOAuthToken).where(
                    GoogleOAuthToken.provider == "google",
                    GoogleOAuthToken.revoked_at.is_(None),
                )
            )
            if row is None or not row.refresh_token_encrypted:
                return None
            if not self.settings.google_oauth_client_id or not self.settings.google_oauth_client_secret:
                return None
            return GoogleOAuthTokens(
                access_token=(
                    SecretStr(row.access_token_encrypted) if row.access_token_encrypted else None
                ),
                refresh_token=SecretStr(row.refresh_token_encrypted),
                token_uri=row.token_uri or "https://oauth2.googleapis.com/token",
                client_id=self.settings.google_oauth_client_id,
                client_secret=SecretStr(
                    self.settings.google_oauth_client_secret.get_secret_value()
                ),
                scopes=tuple(row.scopes or ()),
                expiry=row.expires_at,
            )

    async def save(self, tokens: GoogleOAuthTokens) -> None:
        async with self.session_factory() as session:
            row = await session.scalar(
                select(GoogleOAuthToken).where(GoogleOAuthToken.provider == "google")
            )
            if row is None:
                row = GoogleOAuthToken(provider="google")
                session.add(row)

            row.access_token_encrypted = (
                tokens.access_token.get_secret_value() if tokens.access_token else None
            )
            if tokens.refresh_token:
                row.refresh_token_encrypted = tokens.refresh_token.get_secret_value()
            row.token_uri = tokens.token_uri
            row.scopes = list(tokens.scopes)
            row.expires_at = tokens.expiry
            row.revoked_at = None
            await session.commit()

    async def clear(self) -> None:
        async with self.session_factory() as session:
            row = await session.scalar(
                select(GoogleOAuthToken).where(GoogleOAuthToken.provider == "google")
            )
            if row is None:
                return
            row.revoked_at = datetime.now(UTC)
            await session.commit()
