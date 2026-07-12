from collections.abc import Iterable
from datetime import date
from uuid import UUID

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from app.core.booking import BookingRecord, BookingStatus, MeetingType
from app.core.scheduling import AvailableSlot
from app.integrations.telegram.formatting import (
    format_date_with_weekday,
    format_datetime_msk,
    format_time_msk,
)
from app.integrations.telegram.status_labels import booking_status_label

BACK = "Назад"
CANCEL = "Отмена"
MENU = "Меню"


def main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Записаться", callback_data="uf:book")],
            [InlineKeyboardButton(text="Мои заявки", callback_data="uf:my")],
        ]
    )


def consent_keyboard(
    *,
    personal_data_checked: bool,
    policy_checked: bool,
    consent_url: str | None,
    policy_url: str | None,
) -> InlineKeyboardMarkup:
    personal_prefix = "[x]" if personal_data_checked else "[ ]"
    policy_prefix = "[x]" if policy_checked else "[ ]"
    rows = [
        [
            InlineKeyboardButton(
                text=f"{personal_prefix} Согласие на обработку данных",
                callback_data="uf:consent:personal",
            )
        ],
        [
            InlineKeyboardButton(
                text=f"{policy_prefix} Политика обработки данных",
                callback_data="uf:consent:policy",
            )
        ],
    ]
    if consent_url:
        rows.append(
            [InlineKeyboardButton(text="Открыть согласие", url=consent_url)]
        )
    if policy_url:
        rows.append([InlineKeyboardButton(text="Открыть политику", url=policy_url)])
    rows.append(
        [InlineKeyboardButton(text="Продолжить", callback_data="uf:consent:accept")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def text_navigation_keyboard(*, include_back: bool = True) -> ReplyKeyboardMarkup:
    buttons = []
    if include_back:
        buttons.append(KeyboardButton(text=BACK))
    buttons.append(KeyboardButton(text=CANCEL))
    return ReplyKeyboardMarkup(keyboard=[buttons], resize_keyboard=True)


def menu_reply_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=MENU)]],
        resize_keyboard=True,
    )


def email_found_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Оставить", callback_data="uf:email:keep")],
            [InlineKeyboardButton(text="Изменить", callback_data="uf:email:change")],
            _navigation_row(),
        ]
    )


def meeting_types_keyboard(meeting_types: Iterable[MeetingType]) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=item.name, callback_data=f"uf:type:{item.id}")]
        for item in meeting_types
    ]
    rows.append(_navigation_row())
    return InlineKeyboardMarkup(inline_keyboard=rows)


def durations_keyboard(meeting_type: MeetingType) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=f"{duration} минут",
                callback_data=f"uf:duration:{duration}",
            )
        ]
        for duration in meeting_type.allowed_durations_minutes
    ]
    rows.append(_navigation_row())
    return InlineKeyboardMarkup(inline_keyboard=rows)


def dates_keyboard(dates: list[date], *, page: int = 0, page_size: int = 7) -> InlineKeyboardMarkup:
    start = page * page_size
    visible_dates = dates[start : start + page_size]
    rows = [
        [
            InlineKeyboardButton(
                text=format_date_with_weekday(item),
                callback_data=f"uf:date:{item}",
            )
        ]
        for item in visible_dates
    ]
    pager = []
    if page > 0:
        pager.append(InlineKeyboardButton(text="<", callback_data=f"uf:date_page:{page - 1}"))
    if start + page_size < len(dates):
        pager.append(InlineKeyboardButton(text=">", callback_data=f"uf:date_page:{page + 1}"))
    if pager:
        rows.append(pager)
    rows.append(_navigation_row())
    return InlineKeyboardMarkup(inline_keyboard=rows)


def slots_keyboard(slots: Iterable[AvailableSlot]) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=format_time_msk(slot.starts_at),
                callback_data=f"uf:slot:{index}",
            )
        ]
        for index, slot in enumerate(slots)
    ]
    rows.append(_navigation_row())
    return InlineKeyboardMarkup(inline_keyboard=rows)


def comment_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Пропустить", callback_data="uf:comment:skip")],
            _navigation_row(),
        ]
    )


def review_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Отправить", callback_data="uf:submit")],
            _navigation_row(),
        ]
    )


def bookings_keyboard(bookings: Iterable[BookingRecord]) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=f"{format_datetime_msk(booking.starts_at)} - "
                f"{booking_status_label(booking.status)}",
                callback_data=f"uf:booking:{booking.id}",
            )
        ]
        for booking in bookings
    ]
    rows.append([InlineKeyboardButton(text="В меню", callback_data="uf:menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def booking_actions_keyboard(booking: BookingRecord) -> InlineKeyboardMarkup:
    rows = []
    if booking.status in {BookingStatus.PENDING, BookingStatus.CONFIRMED}:
        rows.append(
            [
                InlineKeyboardButton(
                    text="Отменить",
                    callback_data=f"uf:cancel_booking:{booking.id}",
                )
            ]
        )
    if booking.status == BookingStatus.CONFIRMED:
        rows.append(
            [
                InlineKeyboardButton(
                    text="Перенести",
                    callback_data=f"uf:reschedule:{booking.id}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="Назад", callback_data="uf:my")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def confirm_cancel_keyboard(booking_id: UUID) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Подтвердить",
                    callback_data=f"uf:cancel_confirm:{booking_id}",
                )
            ],
            [InlineKeyboardButton(text="Назад", callback_data=f"uf:booking:{booking_id}")],
        ]
    )


def _navigation_row() -> list[InlineKeyboardButton]:
    return [
        InlineKeyboardButton(text=BACK, callback_data="uf:back"),
        InlineKeyboardButton(text=CANCEL, callback_data="uf:cancel"),
    ]
