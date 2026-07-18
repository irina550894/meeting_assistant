from datetime import datetime, timedelta
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import Depends, HTTPException, Request, status

from app.application import (
    AdminBookingUseCaseDeps,
    AdminBookingUseCases,
    AdminSettingsUseCaseDeps,
    AdminSettingsUseCases,
    MiniAppAnalyticsDeps,
    MiniAppAnalyticsService,
    MiniAppAuthService,
    UserBookingUseCaseDeps,
    UserBookingUseCases,
)
from app.core.admin_flow import AdminFlowService
from app.core.booking import BookingService, UserProfile
from app.core.user_flow import UserFlowService
from app.integrations.google_calendar import (
    GoogleCalendarConfirmationGateway,
    GoogleCalendarEventGateway,
    GoogleCalendarScheduleProvider,
)
from app.integrations.telegram.local_memory import LocalCalendarConfirmationGateway
from app.integrations.telegram.local_notifiers import (
    TelegramAdminNotifier,
    TelegramUserFlowNotifier,
)
from app.integrations.telegram.runtime import _google_calendar_runtime
from app.persistence.database import AsyncSessionFactory
from app.persistence.repositories import (
    CommittedBackgroundJobScheduler,
    SqlAlchemyGoogleOAuthTokenStore,
    SqlAlchemyMiniAppEventStore,
    SqlAlchemyTelegramRuntimeStore,
)
from app.persistence.repositories.mini_app import SqlAlchemyMiniAppSessionStore
from app.settings.config import get_settings


def _clock() -> datetime:
    settings = get_settings()
    timezone = ZoneInfo(settings.app_timezone)
    return datetime.now(tz=timezone)


def get_mini_app_auth_service() -> MiniAppAuthService:
    settings = get_settings()
    return MiniAppAuthService(
        bot_token=settings.telegram_bot_token,
        store=SqlAlchemyMiniAppSessionStore(session_factory=AsyncSessionFactory),
        clock=_clock,
        auth_max_age=timedelta(seconds=settings.mini_app_auth_max_age_seconds),
        session_ttl=timedelta(seconds=settings.mini_app_session_ttl_seconds),
        admin_telegram_id=settings.telegram_admin_id,
    )


async def get_current_mini_app_user(request: Request) -> UserProfile:
    settings = get_settings()
    session_token = request.cookies.get(settings.mini_app_cookie_name)
    if not session_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "mini_app_session_missing", "message": "Mini App session is missing."},
        )

    user = await SqlAlchemyMiniAppSessionStore(
        session_factory=AsyncSessionFactory,
    ).get_user_by_session_token(session_token=session_token, now=_clock())
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "mini_app_session_invalid", "message": "Mini App session is invalid."},
        )
    return user


async def get_current_mini_app_admin(
    user: Annotated[UserProfile, Depends(get_current_mini_app_user)],
) -> UserProfile:
    settings = get_settings()
    if settings.telegram_admin_id is None or user.telegram_id != settings.telegram_admin_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "admin_access_denied", "message": "Admin access denied."},
        )
    return user


async def get_user_booking_use_cases(request: Request) -> UserBookingUseCases:
    settings = get_settings()
    store = SqlAlchemyTelegramRuntimeStore(session_factory=AsyncSessionFactory, settings=settings)
    booking_service = BookingService(
        max_active_bookings_per_user=settings.max_active_bookings_per_user,
        pending_booking_ttl=timedelta(hours=settings.pending_booking_ttl_hours),
        cancellation_deadline=timedelta(hours=settings.cancellation_deadline_hours),
    )
    google_calendar = await _google_calendar_runtime_for_http(settings)
    schedule_provider = (
        GoogleCalendarScheduleProvider(base=store, client=google_calendar)
        if google_calendar
        else store
    )
    event_gateway = GoogleCalendarEventGateway(google_calendar) if google_calendar else None
    runtime = getattr(request.app.state, "telegram_runtime", None)
    notifier = (
        TelegramUserFlowNotifier(bot=runtime.bot, settings=settings)
        if runtime is not None
        else None
    )
    background_jobs = (
        CommittedBackgroundJobScheduler(session_factory=AsyncSessionFactory, settings=settings)
        if settings.telegram_storage.strip().lower() == "postgres"
        else None
    )
    return UserBookingUseCases(
        UserBookingUseCaseDeps(
            settings=settings,
            users=store,
            meeting_types=store,
            bookings=store,
            schedule=schedule_provider,
            flow=UserFlowService(booking_service=booking_service),
            booking_service=booking_service,
            clock=_clock,
            notifier=notifier,
            calendar_events=event_gateway,
            background_jobs=background_jobs,
        )
    )


async def get_admin_booking_use_cases(request: Request) -> AdminBookingUseCases:
    settings = get_settings()
    store = SqlAlchemyTelegramRuntimeStore(session_factory=AsyncSessionFactory, settings=settings)
    booking_service = BookingService(
        max_active_bookings_per_user=settings.max_active_bookings_per_user,
        pending_booking_ttl=timedelta(hours=settings.pending_booking_ttl_hours),
        cancellation_deadline=timedelta(hours=settings.cancellation_deadline_hours),
    )
    google_calendar = await _google_calendar_runtime_for_http(settings)
    confirmation_gateway = (
        GoogleCalendarConfirmationGateway(google_calendar)
        if google_calendar
        else LocalCalendarConfirmationGateway()
    )
    event_gateway = GoogleCalendarEventGateway(google_calendar) if google_calendar else None
    runtime = getattr(request.app.state, "telegram_runtime", None)
    notifier = TelegramAdminNotifier(bot=runtime.bot, store=store) if runtime is not None else None
    background_jobs = (
        CommittedBackgroundJobScheduler(session_factory=AsyncSessionFactory, settings=settings)
        if settings.telegram_storage.strip().lower() == "postgres"
        else None
    )
    return AdminBookingUseCases(
        AdminBookingUseCaseDeps(
            users=store,
            meeting_types=store,
            bookings=store,
            admin_flow=AdminFlowService(booking_service=booking_service),
            calendar=confirmation_gateway,
            clock=_clock,
            notifier=notifier,
            calendar_events=event_gateway,
            background_jobs=background_jobs,
        )
    )


def get_admin_settings_use_cases() -> AdminSettingsUseCases:
    settings = get_settings()
    store = SqlAlchemyTelegramRuntimeStore(session_factory=AsyncSessionFactory, settings=settings)
    return AdminSettingsUseCases(AdminSettingsUseCaseDeps(admin_settings=store))


def get_mini_app_analytics_service() -> MiniAppAnalyticsService:
    return MiniAppAnalyticsService(
        MiniAppAnalyticsDeps(
            store=SqlAlchemyMiniAppEventStore(session_factory=AsyncSessionFactory),
            clock=_clock,
        )
    )


async def _google_calendar_runtime_for_http(settings):
    tokens = await SqlAlchemyGoogleOAuthTokenStore(
        session_factory=AsyncSessionFactory,
        settings=settings,
    ).get()
    if tokens is not None:
        from app.integrations.google_calendar import GoogleCalendarClient

        return GoogleCalendarClient(settings=settings, token_provider=lambda: tokens)
    return _google_calendar_runtime(settings)
