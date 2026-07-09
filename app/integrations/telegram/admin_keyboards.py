from collections.abc import Iterable
from uuid import UUID

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.core.booking import BookingRecord, UserProfile


def admin_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Ожидающие заявки", callback_data="adm:pending")],
            [InlineKeyboardButton(text="Все заявки", callback_data="adm:bookings")],
            [InlineKeyboardButton(text="Заблокированные", callback_data="adm:blocked")],
            [InlineKeyboardButton(text="Расписание", callback_data="adm:schedule")],
            [InlineKeyboardButton(text="Ограничения", callback_data="adm:restrictions")],
            [InlineKeyboardButton(text="Типы встреч", callback_data="adm:meeting_types")],
            [InlineKeyboardButton(text="Фильтры заявок", callback_data="adm:filters")],
        ]
    )


def admin_bookings_keyboard(bookings: Iterable[BookingRecord]) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=f"{booking.starts_at:%d.%m %H:%M} - {booking.status.value}",
                callback_data=f"adm:booking:{booking.id}",
            )
        ]
        for booking in bookings
    ]
    rows.append([InlineKeyboardButton(text="В меню", callback_data="adm:menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_booking_actions_keyboard(booking: BookingRecord) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Подтвердить", callback_data=f"adm:approve:{booking.id}")],
            [InlineKeyboardButton(text="Отклонить", callback_data=f"adm:reject:{booking.id}")],
            [InlineKeyboardButton(text="Написать", callback_data=f"adm:message:{booking.id}")],
            [
                InlineKeyboardButton(
                    text="Заблокировать",
                    callback_data=f"adm:block:{booking.user_id}",
                )
            ],
            [InlineKeyboardButton(text="Назад", callback_data="adm:pending")],
        ]
    )


def approve_keyboard(booking_id: UUID) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Оставить ссылку по умолчанию",
                    callback_data=f"adm:approve_default:{booking_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="Изменить ссылку",
                    callback_data=f"adm:approve_custom:{booking_id}",
                )
            ],
            [InlineKeyboardButton(text="Назад", callback_data=f"adm:booking:{booking_id}")],
        ]
    )


def reject_keyboard(booking_id: UUID) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Без причины",
                    callback_data=f"adm:reject_no_reason:{booking_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="Указать причину",
                    callback_data=f"adm:reject_reason:{booking_id}",
                )
            ],
            [InlineKeyboardButton(text="Назад", callback_data=f"adm:booking:{booking_id}")],
        ]
    )


def block_confirm_keyboard(user_id: UUID) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Подтвердить блокировку",
                    callback_data=f"adm:block_confirm:{user_id}",
                )
            ],
            [InlineKeyboardButton(text="В меню", callback_data="adm:menu")],
        ]
    )


def blocked_users_keyboard(users: Iterable[UserProfile]) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=user.full_name or f"id {user.telegram_id}",
                callback_data=f"adm:unblock:{user.id}",
            )
        ]
        for user in users
    ]
    rows.append([InlineKeyboardButton(text="В меню", callback_data="adm:menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def back_to_admin_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="В меню", callback_data="adm:menu")]]
    )
