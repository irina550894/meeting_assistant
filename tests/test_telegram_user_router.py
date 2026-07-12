from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from app.core.booking import MeetingType
from app.core.scheduling import AvailableSlot
from app.core.user_flow import BookingDraft
from app.integrations.telegram import messages
from app.integrations.telegram.keyboards import dates_keyboard, menu_reply_keyboard, slots_keyboard
from app.integrations.telegram.user_router import _edit_or_answer, _review_text


class FakeCallbackMessage:
    def __init__(self) -> None:
        self.answered: list[tuple[str, dict]] = []
        self.edited: list[tuple[str, dict]] = []

    async def answer(self, text: str, **kwargs) -> None:
        self.answered.append((text, kwargs))

    async def edit_text(self, text: str, **kwargs) -> None:
        self.edited.append((text, kwargs))


@pytest.mark.asyncio
async def test_callback_answer_edits_current_message() -> None:
    message = FakeCallbackMessage()
    callback = SimpleNamespace(message=message)
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="Кнопка", callback_data="test")]]
    )

    await _edit_or_answer(callback, "Обновленный текст", reply_markup=keyboard)

    assert message.edited == [("Обновленный текст", {"reply_markup": keyboard})]
    assert message.answered == []


@pytest.mark.asyncio
async def test_callback_answer_sends_new_message_for_reply_keyboard() -> None:
    message = FakeCallbackMessage()
    callback = SimpleNamespace(message=message)
    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Назад")]],
        resize_keyboard=True,
    )

    await _edit_or_answer(callback, "Введите имя", reply_markup=keyboard)

    assert message.edited == []
    assert message.answered == [("Введите имя", {"reply_markup": keyboard})]


def test_user_review_text_sends_to_approval() -> None:
    assert messages.REVIEW == "Все верно? После отправки заявка уйдет на согласование."


def test_dates_keyboard_shows_weekday() -> None:
    keyboard = dates_keyboard([datetime(2026, 7, 13, tzinfo=UTC).date()])

    assert keyboard.inline_keyboard[0][0].text == "13.07.2026 (пн)"


def test_slots_keyboard_shows_moscow_timezone() -> None:
    keyboard = slots_keyboard(
        [
            AvailableSlot(
                starts_at=datetime(2026, 7, 13, 7, 0, tzinfo=UTC),
                ends_at=datetime(2026, 7, 13, 8, 0, tzinfo=UTC),
            )
        ]
    )

    assert keyboard.inline_keyboard[0][0].text == "10:00 МСК"


def test_review_text_shows_moscow_timezone() -> None:
    meeting_type = MeetingType(name="Консультация", allowed_durations_minutes=(60,))
    draft = BookingDraft(
        full_name="Ирина",
        email="client@inbox.ru",
        meeting_type_id=meeting_type.id,
        duration_minutes=60,
        starts_at=datetime(2026, 7, 13, 7, 0, tzinfo=UTC),
        ends_at=datetime(2026, 7, 13, 8, 0, tzinfo=UTC),
    )

    assert "Дата и время: 13.07.2026 10:00 МСК" in _review_text(draft, meeting_type)


def test_menu_reply_keyboard_has_menu_button() -> None:
    keyboard = menu_reply_keyboard()

    assert keyboard.keyboard[0][0].text == "Меню"
