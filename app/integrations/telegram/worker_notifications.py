from __future__ import annotations

from aiogram import Bot

from app.integrations.telegram.formatting import format_datetime_msk
from app.logging.config import get_logger
from app.worker.jobs import ReminderBooking

logger = get_logger(__name__)


class TelegramReminderSender:
    def __init__(self, bot: Bot) -> None:
        self.bot = bot

    async def send_reminder(self, booking: ReminderBooking, *, reminder_kind: str) -> None:
        text = _reminder_text(booking, reminder_kind=reminder_kind)
        try:
            await self.bot.send_message(chat_id=booking.user_telegram_id, text=text)
        except Exception as error:
            logger.error(
                "Telegram reminder delivery failed",
                extra={
                    "event": "telegram_api_error",
                    "operation": "send_reminder",
                    "booking_id": str(booking.booking_id),
                    "reminder_kind": reminder_kind,
                    "error_type": type(error).__name__,
                },
            )
            raise


def _reminder_text(booking: ReminderBooking, *, reminder_kind: str) -> str:
    starts_at = format_datetime_msk(booking.starts_at)
    title = "Напоминание о встрече"
    if reminder_kind == "24h":
        title = "Напоминание: встреча через 24 часа"
    elif reminder_kind == "1h":
        title = "Напоминание: встреча через 1 час"

    parts = [title, f"Начало: {starts_at}"]
    if booking.meeting_url:
        parts.append(f"Ссылка: {booking.meeting_url}")
    return "\n".join(parts)
