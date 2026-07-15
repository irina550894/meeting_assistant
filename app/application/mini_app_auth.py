import hashlib
import hmac
import json
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol
from urllib.parse import parse_qsl

from pydantic import SecretStr

from app.core.booking import BookingService, UserProfile
from app.logging.config import get_logger

logger = get_logger(__name__)


class MiniAppAuthError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class MiniAppTelegramUser:
    telegram_id: int
    username: str | None
    full_name: str | None
    auth_date: datetime


@dataclass(frozen=True, slots=True)
class MiniAppAuthResult:
    user: UserProfile
    session_token: str
    expires_at: datetime
    is_admin: bool


class MiniAppSessionStore(Protocol):
    async def get_user_by_telegram_id(self, telegram_id: int) -> UserProfile | None: ...

    async def save_user(self, user: UserProfile) -> None: ...

    async def create_session(
        self,
        *,
        user_id,
        session_token: str,
        telegram_auth_date: datetime,
        expires_at: datetime,
        now: datetime,
    ) -> None: ...


class MiniAppAuthService:
    def __init__(
        self,
        *,
        bot_token: SecretStr | None,
        store: MiniAppSessionStore,
        clock: Callable[[], datetime],
        auth_max_age: timedelta,
        session_ttl: timedelta,
        admin_telegram_id: int | None = None,
        booking_service: BookingService | None = None,
    ) -> None:
        self.bot_token = bot_token
        self.store = store
        self.clock = clock
        self.auth_max_age = auth_max_age
        self.session_ttl = session_ttl
        self.admin_telegram_id = admin_telegram_id
        self.booking_service = booking_service or BookingService()

    async def authenticate(self, raw_init_data: str) -> MiniAppAuthResult:
        telegram_user = self.validate_init_data(raw_init_data)
        now = self.clock()
        existing_user = await self.store.get_user_by_telegram_id(telegram_user.telegram_id)
        user = self.booking_service.create_or_update_user(
            telegram_id=telegram_user.telegram_id,
            telegram_username=telegram_user.username,
            now=now,
            existing_user=existing_user,
        )
        if telegram_user.full_name and not user.full_name:
            user.full_name = telegram_user.full_name
            user.updated_at = now
        await self.store.save_user(user)

        session_token = secrets.token_urlsafe(32)
        expires_at = now + self.session_ttl
        await self.store.create_session(
            user_id=user.id,
            session_token=session_token,
            telegram_auth_date=telegram_user.auth_date,
            expires_at=expires_at,
            now=now,
        )
        logger.info(
            "Mini App user authenticated",
            extra={
                "event": "mini_app_auth_success",
                "user_id": str(user.id),
                "is_admin": self.is_admin(telegram_user.telegram_id),
            },
        )
        return MiniAppAuthResult(
            user=user,
            session_token=session_token,
            expires_at=expires_at,
            is_admin=self.is_admin(telegram_user.telegram_id),
        )

    def validate_init_data(self, raw_init_data: str) -> MiniAppTelegramUser:
        if self.bot_token is None:
            raise MiniAppAuthError("bot_token_missing", "Telegram bot token is not configured.")

        fields = dict(parse_qsl(raw_init_data, keep_blank_values=True, strict_parsing=False))
        received_hash = fields.pop("hash", None)
        if not received_hash:
            raise MiniAppAuthError("hash_missing", "Telegram initData hash is missing.")

        data_check_string = "\n".join(f"{key}={value}" for key, value in sorted(fields.items()))
        secret_key = hmac.new(
            b"WebAppData",
            self.bot_token.get_secret_value().encode(),
            hashlib.sha256,
        ).digest()
        expected_hash = hmac.new(
            secret_key,
            data_check_string.encode(),
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(expected_hash, received_hash):
            logger.warning(
                "Mini App initData hash mismatch",
                extra={"event": "mini_app_auth_denied"},
            )
            raise MiniAppAuthError("invalid_hash", "Telegram initData hash is invalid.")

        auth_date = self._auth_date(fields.get("auth_date"))
        now = self.clock()
        if auth_date > now + timedelta(seconds=30):
            raise MiniAppAuthError("auth_date_in_future", "Telegram initData auth_date is invalid.")
        if now - auth_date > self.auth_max_age:
            raise MiniAppAuthError("auth_date_expired", "Telegram initData is expired.")

        return self._telegram_user(fields, auth_date=auth_date)

    def is_admin(self, telegram_id: int) -> bool:
        return self.admin_telegram_id is not None and telegram_id == self.admin_telegram_id

    def _auth_date(self, raw_value: str | None) -> datetime:
        if raw_value is None:
            raise MiniAppAuthError("auth_date_missing", "Telegram initData auth_date is missing.")
        try:
            timestamp = int(raw_value)
        except ValueError as error:
            raise MiniAppAuthError(
                "auth_date_invalid",
                "Telegram initData auth_date is invalid.",
            ) from error
        return datetime.fromtimestamp(timestamp, tz=UTC)

    def _telegram_user(
        self,
        fields: dict[str, str],
        *,
        auth_date: datetime,
    ) -> MiniAppTelegramUser:
        raw_user = fields.get("user")
        if not raw_user:
            raise MiniAppAuthError("user_missing", "Telegram initData user is missing.")
        try:
            user_data = json.loads(raw_user)
            telegram_id = int(user_data["id"])
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise MiniAppAuthError("user_invalid", "Telegram initData user is invalid.") from error

        first_name = (user_data.get("first_name") or "").strip()
        last_name = (user_data.get("last_name") or "").strip()
        full_name = " ".join(part for part in (first_name, last_name) if part) or None
        username = user_data.get("username")
        return MiniAppTelegramUser(
            telegram_id=telegram_id,
            username=username.strip() if isinstance(username, str) and username.strip() else None,
            full_name=full_name,
            auth_date=auth_date,
        )


def session_token_hash(session_token: str) -> str:
    return hashlib.sha256(session_token.encode()).hexdigest()
