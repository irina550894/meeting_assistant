from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from pydantic import SecretStr

from app.core.admin_flow import AdminFlowService
from app.core.booking import BookingService
from app.core.user_flow import UserFlowService
from app.diagnostics import DiagnosticsService
from app.integrations.google_calendar import (
    GoogleCalendarClient,
    GoogleCalendarConfirmationGateway,
    GoogleCalendarEventGateway,
    GoogleCalendarScheduleProvider,
    GoogleOAuthTokens,
)
from app.integrations.telegram.admin_router import create_admin_router
from app.integrations.telegram.critical_notifications import notify_critical_admin
from app.integrations.telegram.local_memory import (
    InMemoryRuntimeStore,
    LocalCalendarConfirmationGateway,
)
from app.integrations.telegram.local_notifiers import (
    TelegramAdminNotifier,
    TelegramUserFlowNotifier,
)
from app.integrations.telegram.ports import AdminFlowDependencies, UserFlowDependencies
from app.integrations.telegram.user_router import create_user_router
from app.logging.config import configure_logging, get_logger
from app.persistence.database import AsyncSessionFactory
from app.persistence.repositories import (
    CommittedBackgroundJobScheduler,
    SqlAlchemyTelegramRuntimeStore,
)
from app.settings.config import get_settings

logger = get_logger(__name__)


async def run_local_polling() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)

    if settings.telegram_bot_token is None:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is required to run the bot.")
    if settings.personal_data_consent_url is None or settings.personal_data_policy_url is None:
        raise RuntimeError(
            "PERSONAL_DATA_CONSENT_URL and PERSONAL_DATA_POLICY_URL are required."
        )

    bot = Bot(
        token=settings.telegram_bot_token.get_secret_value(),
        session=AiohttpSession(timeout=settings.telegram_request_timeout_seconds),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    storage = settings.telegram_storage.strip().lower()
    if storage == "postgres":
        store = SqlAlchemyTelegramRuntimeStore(
            session_factory=AsyncSessionFactory,
            settings=settings,
        )
        await store.ensure_seed_data()
        background_jobs = CommittedBackgroundJobScheduler(
            session_factory=AsyncSessionFactory,
            settings=settings,
        )
    else:
        store = InMemoryRuntimeStore(settings)
        storage = "in_memory"
        background_jobs = None
    booking_service = BookingService(
        max_active_bookings_per_user=settings.max_active_bookings_per_user,
        pending_booking_ttl=timedelta(hours=settings.pending_booking_ttl_hours),
        cancellation_deadline=timedelta(hours=settings.cancellation_deadline_hours),
    )
    timezone = ZoneInfo(settings.app_timezone)

    def clock() -> datetime:
        return datetime.now(tz=timezone)

    google_calendar = _google_calendar_runtime(settings)
    schedule_provider = (
        GoogleCalendarScheduleProvider(base=store, client=google_calendar)
        if google_calendar
        else store
    )
    confirmation_gateway = (
        GoogleCalendarConfirmationGateway(google_calendar)
        if google_calendar
        else LocalCalendarConfirmationGateway()
    )
    event_gateway = GoogleCalendarEventGateway(google_calendar) if google_calendar else None

    user_deps = UserFlowDependencies(
        settings=settings,
        users=store,
        meeting_types=store,
        bookings=store,
        schedule=schedule_provider,
        flow=UserFlowService(booking_service=booking_service),
        booking_service=booking_service,
        clock=clock,
        notifier=TelegramUserFlowNotifier(bot=bot, settings=settings),
        calendar_events=event_gateway,
        background_jobs=background_jobs,
    )
    admin_deps = AdminFlowDependencies(
        settings=settings,
        users=store,
        meeting_types=store,
        bookings=store,
        admin_flow=AdminFlowService(booking_service=booking_service),
        calendar=confirmation_gateway,
        clock=clock,
        notifier=TelegramAdminNotifier(bot=bot, store=store),
        background_jobs=background_jobs,
        diagnostics=DiagnosticsService(
            settings,
            session_factory=AsyncSessionFactory,
            telegram_bot=bot,
            google_calendar=google_calendar,
            now=clock,
        ),
    )

    dispatcher = Dispatcher()
    dispatcher.include_router(create_admin_router(admin_deps))
    dispatcher.include_router(create_user_router(user_deps))

    logger.info(
        "Telegram bot polling started",
        extra={
            "event": "telegram_polling_started",
            "admin_configured": settings.telegram_admin_id is not None,
            "storage": storage,
        },
    )
    try:
        await dispatcher.start_polling(bot)
    except Exception as error:
        logger.critical(
            "Telegram polling failed",
            extra={
                "event": "critical_error",
                "source": "telegram_polling",
                "error_type": type(error).__name__,
            },
        )
        await notify_critical_admin(
            settings,
            source="telegram_polling",
            error_type=type(error).__name__,
            bot=bot,
        )
        raise
    finally:
        await bot.session.close()


def _google_calendar_runtime(settings) -> GoogleCalendarClient | None:
    if not (
        settings.google_oauth_client_id
        and settings.google_oauth_client_secret
        and settings.google_oauth_refresh_token
    ):
        return None
    tokens = GoogleOAuthTokens(
        access_token=None,
        refresh_token=settings.google_oauth_refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=settings.google_oauth_client_id,
        client_secret=SecretStr(settings.google_oauth_client_secret.get_secret_value()),
    )
    return GoogleCalendarClient(settings=settings, token_provider=lambda: tokens)
