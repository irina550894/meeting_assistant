from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from app.core.booking import BookingRecord, BookingStatus, MeetingType, UserProfile
from app.core.scheduling import AvailableSlot
from app.core.user_flow import BookingDraft
from app.integrations.telegram import messages
from app.integrations.telegram.keyboards import (
    MINI_APP_BUTTON_TEXT,
    consent_keyboard,
    dates_keyboard,
    main_menu_keyboard,
    menu_reply_keyboard,
    slots_keyboard,
)
from app.integrations.telegram.local_notifiers import _confirmed_booking_text
from app.integrations.telegram.user_router import _edit_or_answer, _mini_app_url, _review_text
from app.settings.config import Settings


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


def test_main_menu_keyboard_includes_mini_app_webapp_button() -> None:
    keyboard = main_menu_keyboard(mini_app_url="https://calendar.finforbiz.pro/miniapp/")

    button = keyboard.inline_keyboard[0][0]

    assert button.text == MINI_APP_BUTTON_TEXT
    assert button.web_app is not None
    assert button.web_app.url == "https://calendar.finforbiz.pro/miniapp/"
    assert keyboard.inline_keyboard[1][0].text == "Записаться"


def test_consent_keyboard_includes_mini_app_webapp_button() -> None:
    keyboard = consent_keyboard(
        personal_data_checked=False,
        policy_checked=False,
        consent_url="https://example.com/consent",
        policy_url="https://example.com/policy",
        mini_app_url="https://calendar.finforbiz.pro/miniapp/",
    )

    webapp_buttons = [
        button
        for row in keyboard.inline_keyboard
        for button in row
        if button.text == MINI_APP_BUTTON_TEXT
    ]

    assert len(webapp_buttons) == 1
    assert webapp_buttons[0].web_app is not None
    assert webapp_buttons[0].web_app.url == "https://calendar.finforbiz.pro/miniapp/"


def test_mini_app_url_requires_https_public_base_url() -> None:
    assert (
        _mini_app_url(
            Settings(
                mini_app_enabled=True,
                public_base_url="https://calendar.finforbiz.pro",
                mini_app_public_path="/miniapp",
            )
        )
        == "https://calendar.finforbiz.pro/miniapp/"
    )
    assert (
        _mini_app_url(Settings(mini_app_enabled=True, public_base_url="http://localhost"))
        is None
    )
    assert (
        _mini_app_url(Settings(mini_app_enabled=False, public_base_url="https://example.com"))
        is None
    )


def test_confirmed_booking_text_contains_full_booking_details() -> None:
    user = UserProfile(
        telegram_id=1001,
        telegram_username="client_user",
        full_name="Ирина",
        email="client@inbox.ru",
    )
    meeting_type = MeetingType(name="Консультация", allowed_durations_minutes=(60,))
    booking = BookingRecord(
        user_id=user.id,
        meeting_type_id=meeting_type.id,
        duration_minutes=60,
        starts_at=datetime(2026, 7, 13, 7, 0, tzinfo=UTC),
        ends_at=datetime(2026, 7, 13, 8, 0, tzinfo=UTC),
        status=BookingStatus.CONFIRMED,
        user_comment="Обсудить проект",
        meeting_url="https://telemost.example/meeting",
    )

    text = _confirmed_booking_text(
        booking=booking,
        user=user,
        meeting_type=meeting_type,
    )

    assert "Имя: Ирина" in text
    assert "Telegram: @client_user" in text
    assert "Email: client@inbox.ru" in text
    assert "Тип встречи: Консультация" in text
    assert "Длительность: 60 минут" in text
    assert "Дата и время: 13.07.2026 10:00 МСК" in text
    assert "Комментарий: Обсудить проект" in text
    assert "Ссылка на видеовстречу: https://telemost.example/meeting" in text
