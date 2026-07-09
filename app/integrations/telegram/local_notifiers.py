from aiogram import Bot

from app.core.booking import BookingRecord, UserProfile
from app.integrations.telegram.admin_keyboards import admin_booking_actions_keyboard
from app.integrations.telegram.local_memory import InMemoryRuntimeStore
from app.settings.config import Settings


class TelegramUserFlowNotifier:
    def __init__(self, *, bot: Bot, settings: Settings) -> None:
        self.bot = bot
        self.settings = settings

    async def booking_created(self, booking: BookingRecord) -> None:
        if self.settings.telegram_admin_id is None:
            return
        await self.bot.send_message(
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
        await self.bot.send_message(
            chat_id=self.settings.telegram_admin_id,
            text=f"Пользователь отменил заявку {booking.id}.",
        )

    async def reschedule_requested(self, booking: BookingRecord) -> None:
        if self.settings.telegram_admin_id is None:
            return
        await self.bot.send_message(
            chat_id=self.settings.telegram_admin_id,
            text=f"Поступила заявка на перенос {booking.id}.",
            reply_markup=admin_booking_actions_keyboard(booking),
        )


class TelegramAdminNotifier:
    def __init__(self, *, bot: Bot, store: InMemoryRuntimeStore) -> None:
        self.bot = bot
        self.store = store

    async def booking_confirmed(self, booking: BookingRecord) -> None:
        user = await self.store.get(booking.user_id)
        if not isinstance(user, UserProfile):
            return
        await self.bot.send_message(
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
        await self.bot.send_message(chat_id=user.telegram_id, text=text)

    async def user_blocked(self, user: UserProfile) -> None:
        await self.bot.send_message(
            chat_id=user.telegram_id,
            text="К сожалению, сейчас вы не можете создать заявку на встречу.",
        )

    async def send_user_message(self, user: UserProfile, text: str) -> None:
        await self.bot.send_message(chat_id=user.telegram_id, text=text, parse_mode=None)
