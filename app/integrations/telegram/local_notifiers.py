from typing import Protocol
from uuid import UUID

from aiogram import Bot

from app.core.booking import BookingRecord, UserProfile
from app.integrations.telegram.admin_keyboards import admin_booking_actions_keyboard
from app.logging.config import get_logger
from app.settings.config import Settings

logger = get_logger(__name__)


class UserLookupStore(Protocol):
    async def get(self, entity_id: UUID) -> object | None: ...


class TelegramUserFlowNotifier:
    def __init__(self, *, bot: Bot, settings: Settings) -> None:
        self.bot = bot
        self.settings = settings

    async def booking_created(self, booking: BookingRecord) -> None:
        if self.settings.telegram_admin_id is None:
            return
        await _send_telegram_message(
            self.bot,
            chat_id=self.settings.telegram_admin_id,
            text=(
                "Поступила новая заявка на встречу: "
                f"{booking.starts_at:%d.%m.%Y} {booking.starts_at:%H:%M}."
            ),
            reply_markup=admin_booking_actions_keyboard(booking),
        )

    async def booking_cancelled_by_user(self, booking: BookingRecord) -> None:
        if self.settings.telegram_admin_id is None:
            return
        await _send_telegram_message(
            self.bot,
            chat_id=self.settings.telegram_admin_id,
            text=f"Пользователь отменил заявку {booking.id}.",
        )

    async def reschedule_requested(self, booking: BookingRecord) -> None:
        if self.settings.telegram_admin_id is None:
            return
        await _send_telegram_message(
            self.bot,
            chat_id=self.settings.telegram_admin_id,
            text=f"Поступила заявка на перенос {booking.id}.",
            reply_markup=admin_booking_actions_keyboard(booking),
        )


class TelegramAdminNotifier:
    def __init__(self, *, bot: Bot, store: UserLookupStore) -> None:
        self.bot = bot
        self.store = store

    async def booking_confirmed(self, booking: BookingRecord) -> None:
        user = await self.store.get(booking.user_id)
        if not isinstance(user, UserProfile):
            return
        await _send_telegram_message(
            self.bot,
            chat_id=user.telegram_id,
            text="Встреча подтверждена. Приглашение отправлено на email.",
        )

    async def booking_rejected(self, booking: BookingRecord, reason: str | None) -> None:
        user = await self.store.get(booking.user_id)
        if not isinstance(user, UserProfile):
            return
        text = "Заявка отклонена."
        if reason:
            text = f"Заявка отклонена. Причина: {reason}."
        await _send_telegram_message(self.bot, chat_id=user.telegram_id, text=text)

    async def user_blocked(self, user: UserProfile) -> None:
        await _send_telegram_message(
            self.bot,
            chat_id=user.telegram_id,
            text="К сожалению, сейчас вы не можете создать заявку на встречу.",
        )

    async def send_user_message(self, user: UserProfile, text: str) -> None:
        await _send_telegram_message(
            self.bot,
            chat_id=user.telegram_id,
            text=text,
            parse_mode=None,
        )


async def _send_telegram_message(bot: Bot, **kwargs):
    try:
        return await bot.send_message(**kwargs)
    except Exception as error:
        logger.error(
            "Telegram message delivery failed",
            extra={
                "event": "telegram_api_error",
                "operation": "send_message",
                "error_type": type(error).__name__,
            },
        )
        raise
