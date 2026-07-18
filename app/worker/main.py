import asyncio
from datetime import UTC, datetime

from aiogram import Bot
from aiogram.client.session.aiohttp import AiohttpSession
from pydantic import SecretStr

from app.integrations.google_calendar import (
    GoogleCalendarClient,
    GoogleCalendarEventChecker,
    GoogleOAuthTokens,
)
from app.integrations.telegram.critical_notifications import notify_critical_admin
from app.integrations.telegram.worker_notifications import TelegramReminderSender
from app.logging.config import configure_logging, get_logger
from app.persistence.database import AsyncSessionFactory
from app.persistence.repositories import (
    SqlAlchemyBackgroundJobRepository,
    SqlAlchemyGoogleOAuthTokenStore,
)
from app.settings.config import Settings, get_settings
from app.worker.jobs import GoogleEventChecker, ReminderSender, WorkerRunResult, WorkerService
from app.worker.scheduler import BackgroundJobScheduler

configure_logging()
logger = get_logger(__name__)


async def run_worker_once_async(service: WorkerService | None = None) -> WorkerRunResult:
    settings = get_settings()
    if service is not None:
        return await service.run_once()

    async with AsyncSessionFactory() as session:
        repository = SqlAlchemyBackgroundJobRepository(session)
        bot = _telegram_bot(settings)
        try:
            worker = WorkerService(
                repository=repository,
                settings=settings,
                reminder_sender=_reminder_sender(bot),
                google_event_checker=await _google_event_checker(settings),
                now=lambda: datetime.now(UTC),
            )
            result = await worker.run_once()
            await session.commit()
            return result
        finally:
            if bot is not None:
                await bot.session.close()


def run_worker_once(service: WorkerService | None = None) -> WorkerRunResult:
    return asyncio.run(run_worker_once_async(service))


async def run_worker_loop_async() -> None:
    settings = get_settings()
    await recover_jobs_once_async()
    while True:
        await run_worker_once_async()
        await asyncio.sleep(settings.worker_poll_interval_seconds)


async def recover_jobs_once_async() -> int:
    settings = get_settings()
    async with AsyncSessionFactory() as session:
        repository = SqlAlchemyBackgroundJobRepository(session)
        scheduler = BackgroundJobScheduler(repository=repository, settings=settings)
        recovered = await scheduler.recover_jobs(now=datetime.now(UTC))
        await session.commit()
        logger.info(
            "Background jobs recovered",
            extra={"event": "background_jobs_recovered", "jobs": recovered},
        )
        return recovered


def log_worker_tick() -> None:
    settings = get_settings()
    logger.info(
        "Worker tick completed",
        extra={
            "event": "worker_tick",
            "service": "worker",
            "poll_interval_seconds": settings.worker_poll_interval_seconds,
        },
    )


def _telegram_bot(settings: Settings) -> Bot | None:
    if settings.telegram_bot_token is None:
        return None
    return Bot(
        token=settings.telegram_bot_token.get_secret_value(),
        session=AiohttpSession(timeout=settings.telegram_request_timeout_seconds),
    )


def _reminder_sender(bot: Bot | None) -> ReminderSender | None:
    if bot is None:
        return None
    return TelegramReminderSender(bot)


async def _google_event_checker(settings: Settings) -> GoogleEventChecker | None:
    stored_tokens = await SqlAlchemyGoogleOAuthTokenStore(
        session_factory=AsyncSessionFactory,
        settings=settings,
    ).get()
    if stored_tokens is not None:
        client = GoogleCalendarClient(settings=settings, token_provider=lambda: stored_tokens)
        return GoogleCalendarEventChecker(client)

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
    client = GoogleCalendarClient(settings=settings, token_provider=lambda: tokens)
    return GoogleCalendarEventChecker(client)


def main() -> None:
    settings = get_settings()
    logger.info(
        "Worker started",
        extra={
            "event": "worker_started",
            "service": "worker",
            "environment": settings.app_env,
        },
    )
    try:
        asyncio.run(run_worker_loop_async())
    except KeyboardInterrupt:
        logger.info("Worker stopped", extra={"event": "worker_stopped", "service": "worker"})
    except Exception as error:
        logger.critical(
            "Worker failed",
            extra={
                "event": "critical_error",
                "source": "worker",
                "service": "worker",
                "error_type": type(error).__name__,
            },
        )
        asyncio.run(
            notify_critical_admin(
                settings,
                source="worker",
                error_type=type(error).__name__,
            )
        )
        raise


if __name__ == "__main__":
    main()
