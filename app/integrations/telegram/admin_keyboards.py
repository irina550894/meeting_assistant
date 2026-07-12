from collections.abc import Iterable
from uuid import UUID

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.core.booking import BookingRecord, BookingStatus, UserProfile
from app.core.datetime_formatting import format_datetime_msk
from app.integrations.telegram.ports import AdminMeetingType, AdminScheduleRestriction
from app.integrations.telegram.status_labels import booking_status_label


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
                text=f"{format_datetime_msk(booking.starts_at)} - "
                f"{booking_status_label(booking.status)}",
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


def restrictions_keyboard(restrictions: Iterable[AdminScheduleRestriction]) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text="Добавить закрытый день",
                callback_data="adm:restriction_add",
            )
        ]
    ]
    rows.extend(
        [
            InlineKeyboardButton(
                text=f"Удалить {restriction.restriction_date:%d.%m.%Y}",
                callback_data=f"adm:restriction_delete:{restriction.id}",
            )
        ]
        for restriction in restrictions
    )
    rows.append([InlineKeyboardButton(text="В меню", callback_data="adm:menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def meeting_types_admin_keyboard(
    meeting_types: Iterable[AdminMeetingType],
) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="Добавить тип встречи", callback_data="adm:meeting_type_add")]
    ]
    rows.extend(
        [
            InlineKeyboardButton(
                text=(
                    f"{'Отключить' if meeting_type.is_active else 'Включить'} "
                    f"{meeting_type.name}"
                ),
                callback_data=(
                    f"adm:meeting_type_toggle:{meeting_type.id}:"
                    f"{0 if meeting_type.is_active else 1}"
                ),
            )
        ]
        for meeting_type in meeting_types
    )
    rows.append([InlineKeyboardButton(text="В меню", callback_data="adm:menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def booking_filters_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            *[
                [
                    InlineKeyboardButton(
                        text=booking_status_label(status),
                        callback_data=f"adm:filter:{status.value}",
                    )
                ]
                for status in BookingStatus
            ],
            [InlineKeyboardButton(text="В меню", callback_data="adm:menu")],
        ],
    )


def back_to_admin_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="В меню", callback_data="adm:menu")]]
    )
