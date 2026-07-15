from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from app.core.booking import UserProfile
from app.logging.config import get_logger

logger = get_logger(__name__)


class MiniAppAnalyticsStore(Protocol):
    async def record_event(
        self,
        *,
        user: UserProfile,
        event_name: str,
        payload: dict[str, Any],
        created_at: datetime,
    ) -> None: ...


@dataclass(frozen=True, slots=True)
class MiniAppAnalyticsDeps:
    store: MiniAppAnalyticsStore
    clock: Callable[[], datetime]


class MiniAppAnalyticsService:
    def __init__(self, deps: MiniAppAnalyticsDeps) -> None:
        self.deps = deps

    async def track_event(
        self,
        *,
        user: UserProfile,
        event_name: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        try:
            await self.deps.store.record_event(
                user=user,
                event_name=event_name,
                payload=payload or {},
                created_at=self.deps.clock(),
            )
        except Exception as error:
            logger.warning(
                "Mini App analytics event was not recorded",
                extra={
                    "event": "mini_app_analytics_error",
                    "event_name": event_name,
                    "user_id": str(user.id),
                    "error_type": type(error).__name__,
                },
            )
