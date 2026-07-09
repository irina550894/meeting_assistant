from __future__ import annotations

from aiogram import Bot

from app.worker.jobs import ReminderBooking


class TelegramReminderSender:
    def __init__(self, bot: Bot) -> None:
        self.bot = bot

    async def send_reminder(self, booking: ReminderBooking, *, reminder_kind: str) -> None:
        text = _reminder_text(booking, reminder_kind=reminder_kind)
        await self.bot.send_message(chat_id=booking.user_telegram_id, text=text)


def _reminder_text(booking: ReminderBooking, *, reminder_kind: str) -> str:
    starts_at = booking.starts_at.strftime("%d.%m.%Y %H:%M")
    title = "Напоминание о встрече"
    if reminder_kind == "24h":
        title = "Напоминание: встреча через 24 часа"
    elif reminder_kind == "1h":
        title = "Напоминание: встреча через 1 час"

    parts = [title, f"Начало: {starts_at}"]
    if booking.meeting_url:
        parts.append(f"Ссылка: {booking.meeting_url}")
    return "\n".join(parts)
