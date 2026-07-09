from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from app.core.admin_flow import AdminFlowService
from app.core.booking import BookingService
from app.core.user_flow import UserFlowService
from app.integrations.telegram.admin_router import create_admin_router
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
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    store = InMemoryRuntimeStore(settings)
    booking_service = BookingService(
        max_active_bookings_per_user=settings.max_active_bookings_per_user,
        pending_booking_ttl=timedelta(hours=settings.pending_booking_ttl_hours),
        cancellation_deadline=timedelta(hours=settings.cancellation_deadline_hours),
    )
    timezone = ZoneInfo(settings.app_timezone)

    def clock() -> datetime:
        return datetime.now(tz=timezone)

    user_deps = UserFlowDependencies(
        settings=settings,
        users=store,
        meeting_types=store,
        bookings=store,
        schedule=store,
        flow=UserFlowService(booking_service=booking_service),
        booking_service=booking_service,
        clock=clock,
        notifier=TelegramUserFlowNotifier(bot=bot, settings=settings),
    )
    admin_deps = AdminFlowDependencies(
        settings=settings,
        users=store,
        meeting_types=store,
        bookings=store,
        admin_flow=AdminFlowService(booking_service=booking_service),
        calendar=LocalCalendarConfirmationGateway(),
        clock=clock,
        notifier=TelegramAdminNotifier(bot=bot, store=store),
    )

    dispatcher = Dispatcher()
    dispatcher.include_router(create_admin_router(admin_deps))
    dispatcher.include_router(create_user_router(user_deps))

    logger.info(
        "Telegram bot polling started",
        extra={
            "event": "telegram_polling_started",
            "admin_configured": settings.telegram_admin_id is not None,
            "storage": "in_memory",
        },
    )
    await dispatcher.start_polling(bot)
