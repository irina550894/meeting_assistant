from collections.abc import Callable
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.application.mini_app_auth import session_token_hash
from app.application.sources import ActionSource
from app.core.booking import UserProfile
from app.persistence.models import MiniAppEvent, MiniAppSession, User

SessionFactory = Callable[[], Any]


class SqlAlchemyMiniAppSessionStore:
    def __init__(self, *, session_factory: SessionFactory) -> None:
        self.session_factory = session_factory

    async def get_user_by_telegram_id(self, telegram_id: int) -> UserProfile | None:
        async with self.session_factory() as session:
            user = await session.scalar(select(User).where(User.telegram_id == telegram_id))
            return _user_profile(user) if user else None

    async def get_user_by_session_token(
        self,
        *,
        session_token: str,
        now: datetime,
    ) -> UserProfile | None:
        async with self.session_factory() as session:
            async with session.begin():
                mini_app_session = await session.scalar(
                    select(MiniAppSession)
                    .options(selectinload(MiniAppSession.user))
                    .where(MiniAppSession.session_hash == session_token_hash(session_token))
                    .where(MiniAppSession.revoked_at.is_(None))
                    .where(MiniAppSession.expires_at > now)
                )
                if mini_app_session is None:
                    return None
                mini_app_session.last_seen_at = now
                return _user_profile(mini_app_session.user)

    async def save_user(self, user: UserProfile) -> None:
        async with self.session_factory() as session:
            async with session.begin():
                model = await session.get(User, user.id)
                if model is None:
                    model = User(id=user.id, telegram_id=user.telegram_id)
                    session.add(model)
                _apply_user_fields(model, user)

    async def create_session(
        self,
        *,
        user_id,
        session_token: str,
        telegram_auth_date: datetime,
        expires_at: datetime,
        now: datetime,
    ) -> None:
        async with self.session_factory() as session:
            async with session.begin():
                session.add(
                    MiniAppSession(
                        user_id=user_id,
                        session_hash=session_token_hash(session_token),
                        telegram_auth_date=telegram_auth_date,
                        expires_at=expires_at,
                        last_seen_at=now,
                    )
                )

class SqlAlchemyMiniAppEventStore:
    def __init__(self, *, session_factory: SessionFactory) -> None:
        self.session_factory = session_factory

    async def record_event(
        self,
        *,
        user: UserProfile,
        event_name: str,
        payload: dict[str, Any],
        created_at: datetime,
    ) -> None:
        async with self.session_factory() as session:
            async with session.begin():
                session.add(
                    MiniAppEvent(
                        user_id=user.id,
                        event_name=event_name,
                        source=ActionSource.MINI_APP.value,
                        payload=payload,
                        created_at=created_at,
                    )
                )


def _apply_user_fields(model: User, user: UserProfile) -> None:
    model.telegram_id = user.telegram_id
    model.telegram_username = user.telegram_username
    model.full_name = user.full_name
    model.email = user.email
    model.is_blocked = user.is_blocked
    model.telegram_username_updated_at = user.telegram_username_updated_at
    model.consent_accepted_at = user.consent_accepted_at
    model.consent_url = user.consent_url
    model.policy_url = user.policy_url
    if user.created_at is not None:
        model.created_at = user.created_at
    if user.updated_at is not None:
        model.updated_at = user.updated_at


def _user_profile(user: User) -> UserProfile:
    return UserProfile(
        id=user.id,
        telegram_id=user.telegram_id,
        telegram_username=user.telegram_username,
        full_name=user.full_name,
        email=user.email,
        is_blocked=user.is_blocked,
        created_at=user.created_at,
        updated_at=user.updated_at,
        telegram_username_updated_at=user.telegram_username_updated_at,
        consent_accepted_at=user.consent_accepted_at,
        consent_url=user.consent_url,
        policy_url=user.policy_url,
    )
