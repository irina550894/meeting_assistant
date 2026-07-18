from typing import Protocol
from uuid import UUID

from aiogram import Bot

from app.core.booking import BookingRecord, MeetingType, UserProfile
from app.core.datetime_formatting import format_datetime_msk
from app.integrations.telegram.admin_keyboards import admin_booking_actions_keyboard
from app.logging.config import get_logger
from app.settings.config import Settings

logger = get_logger(__name__)


class RuntimeLookupStore(Protocol):
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
                f"{format_datetime_msk(booking.starts_at)}."
            ),
            reply_markup=admin_booking_actions_keyboard(booking),
        )

    async def booking_cancelled_by_user(self, booking: BookingRecord) -> None:
        if self.settings.telegram_admin_id is None:
            return
        await _send_telegram_message(
            self.bot,
            chat_id=self.settings.telegram_admin_id,
            text=f"Пользователь отменил заявку {_booking_number_label(booking)}.",
        )

    async def reschedule_requested(self, booking: BookingRecord) -> None:
        if self.settings.telegram_admin_id is None:
            return
        await _send_telegram_message(
            self.bot,
            chat_id=self.settings.telegram_admin_id,
            text=f"Поступила заявка на перенос {_booking_number_label(booking)}.",
            reply_markup=admin_booking_actions_keyboard(booking),
        )


class TelegramAdminNotifier:
    def __init__(self, *, bot: Bot, store: RuntimeLookupStore) -> None:
        self.bot = bot
        self.store = store

    async def booking_confirmed(self, booking: BookingRecord) -> None:
        user = await self.store.get(booking.user_id)
        meeting_type = await self.store.get(booking.meeting_type_id)
        if not isinstance(user, UserProfile) or not isinstance(meeting_type, MeetingType):
            return
        await _send_telegram_message(
            self.bot,
            chat_id=user.telegram_id,
            text=_confirmed_booking_text(
                booking=booking,
                user=user,
                meeting_type=meeting_type,
            ),
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


def _confirmed_booking_text(
    *,
    booking: BookingRecord,
    user: UserProfile,
    meeting_type: MeetingType,
) -> str:
    username = f"@{user.telegram_username}" if user.telegram_username else "username не указан"
    return "\n".join(
        [
            "Встреча подтверждена.",
            "",
            f"Имя: {user.full_name or '-'}",
            f"Telegram: {username}",
            f"Email: {user.email or '-'}",
            f"Тип встречи: {meeting_type.name}",
            f"Длительность: {booking.duration_minutes} минут",
            f"Дата и время: {format_datetime_msk(booking.starts_at)}",
            f"Комментарий: {booking.user_comment or '-'}",
            f"Ссылка на видеовстречу: {booking.meeting_url or '-'}",
            "",
            "Приглашение отправлено на email через Google Calendar.",
        ]
    )


def _booking_number_label(booking: BookingRecord) -> str:
    if booking.display_number is not None:
        return f"№{booking.display_number}"
    return str(booking.id)
