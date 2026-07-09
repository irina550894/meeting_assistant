from types import SimpleNamespace

import pytest
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from app.integrations.telegram import messages
from app.integrations.telegram.user_router import _edit_or_answer


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
