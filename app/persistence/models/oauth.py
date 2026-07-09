from datetime import datetime

from sqlalchemy import DateTime, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.persistence.models.base import Base, TimestampMixin, UuidPrimaryKeyMixin


class GoogleOAuthToken(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "google_oauth_tokens"

    provider: Mapped[str] = mapped_column(String(50), default="google", unique=True, nullable=False)
    access_token_encrypted: Mapped[str | None] = mapped_column(Text)
    refresh_token_encrypted: Mapped[str | None] = mapped_column(Text)
    token_uri: Mapped[str | None] = mapped_column(String(2048))
    scopes: Mapped[list[str] | None] = mapped_column(JSONB)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
