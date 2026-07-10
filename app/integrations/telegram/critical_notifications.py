from __future__ import annotations

from aiogram import Bot
from aiogram.client.session.aiohttp import AiohttpSession

from app.logging.config import get_logger
from app.settings.config import Settings

logger = get_logger(__name__)


async def notify_critical_admin(
    settings: Settings,
    *,
    source: str,
    error_type: str,
    bot: Bot | None = None,
) -> bool:
    if settings.telegram_bot_token is None or settings.telegram_admin_id is None:
        logger.warning(
            "Critical admin notification skipped",
            extra={
                "event": "critical_admin_notification_skipped",
                "source": source,
                "telegram_bot_token_configured": settings.telegram_bot_token is not None,
                "telegram_admin_id_configured": settings.telegram_admin_id is not None,
            },
        )
        return False

    owns_bot = bot is None
    if bot is None:
        bot = Bot(
            token=settings.telegram_bot_token.get_secret_value(),
            session=AiohttpSession(timeout=settings.telegram_request_timeout_seconds),
        )

    try:
        await bot.send_message(
            chat_id=settings.telegram_admin_id,
            text=(
                "Обнаружена критическая ошибка.\n"
                f"Источник: {source}\n"
                f"Тип: {error_type}\n"
                "Проверьте технические логи по operation_id и event=critical_error."
            ),
            parse_mode=None,
        )
        logger.info(
            "Critical admin notification sent",
            extra={"event": "critical_admin_notification_sent", "source": source},
        )
        return True
    except Exception as error:
        logger.error(
            "Telegram critical admin notification failed",
            extra={
                "event": "telegram_api_error",
                "operation": "send_critical_admin_notification",
                "source": source,
                "error_type": type(error).__name__,
            },
        )
        return False
    finally:
        if owns_bot:
            await bot.session.close()
