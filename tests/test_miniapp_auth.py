import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import pytest
from pydantic import SecretStr

from app.application import MiniAppAuthError, MiniAppAuthService

NOW = datetime(2026, 7, 14, 12, 0, tzinfo=UTC)
BOT_TOKEN = "123456:test-token"


class FakeMiniAppSessionStore:
    def __init__(self):
        self.user = None
        self.saved_user = None
        self.sessions = []

    async def get_user_by_telegram_id(self, telegram_id: int):
        return self.user

    async def save_user(self, user):
        self.saved_user = user
        self.user = user

    async def create_session(self, **kwargs):
        self.sessions.append(kwargs)


def clock() -> datetime:
    return NOW


def auth_service(store: FakeMiniAppSessionStore) -> MiniAppAuthService:
    return MiniAppAuthService(
        bot_token=SecretStr(BOT_TOKEN),
        store=store,
        clock=clock,
        auth_max_age=timedelta(hours=24),
        session_ttl=timedelta(hours=12),
        admin_telegram_id=1001,
    )


def signed_init_data(*, bot_token: str = BOT_TOKEN, auth_date: datetime = NOW) -> str:
    fields = {
        "auth_date": str(int(auth_date.timestamp())),
        "query_id": "AAHdF6IQAAAAAN0XohDhrOrc",
        "user": json.dumps(
            {
                "id": 1001,
                "first_name": "Irina",
                "last_name": "Admin",
                "username": "irina",
            },
            separators=(",", ":"),
        ),
    }
    data_check_string = "\n".join(f"{key}={value}" for key, value in sorted(fields.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    return urlencode(fields)


@pytest.mark.asyncio
async def test_authenticate_valid_init_data_creates_user_and_session() -> None:
    store = FakeMiniAppSessionStore()

    result = await auth_service(store).authenticate(signed_init_data())

    assert result.user.telegram_id == 1001
    assert result.user.telegram_username == "irina"
    assert result.user.full_name == "Irina Admin"
    assert result.is_admin is True
    assert result.session_token
    assert result.expires_at == NOW + timedelta(hours=12)
    assert store.saved_user == result.user
    assert len(store.sessions) == 1
    assert store.sessions[0]["user_id"] == result.user.id
    assert store.sessions[0]["expires_at"] == result.expires_at


def test_validate_init_data_rejects_invalid_hash() -> None:
    store = FakeMiniAppSessionStore()
    init_data = signed_init_data().replace("hash=", "hash=bad")

    with pytest.raises(MiniAppAuthError) as error:
        auth_service(store).validate_init_data(init_data)

    assert error.value.code == "invalid_hash"


def test_validate_init_data_rejects_expired_auth_date() -> None:
    store = FakeMiniAppSessionStore()

    with pytest.raises(MiniAppAuthError) as error:
        auth_service(store).validate_init_data(
            signed_init_data(auth_date=NOW - timedelta(days=2))
        )

    assert error.value.code == "auth_date_expired"


def test_validate_init_data_requires_bot_token() -> None:
    store = FakeMiniAppSessionStore()
    service = MiniAppAuthService(
        bot_token=None,
        store=store,
        clock=clock,
        auth_max_age=timedelta(hours=24),
        session_ttl=timedelta(hours=12),
    )

    with pytest.raises(MiniAppAuthError) as error:
        service.validate_init_data(signed_init_data())

    assert error.value.code == "bot_token_missing"
