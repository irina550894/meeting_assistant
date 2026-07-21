from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.core.booking import BookingRecord, BookingStatus
from app.integrations.telegram.admin_keyboards import admin_booking_actions_keyboard

NOW = datetime(2026, 7, 21, 12, 0, tzinfo=UTC)


def test_confirmed_booking_admin_keyboard_uses_cancel_not_reject() -> None:
    booking = BookingRecord(
        id=uuid4(),
        user_id=uuid4(),
        meeting_type_id=uuid4(),
        duration_minutes=60,
        starts_at=NOW + timedelta(days=1),
        ends_at=NOW + timedelta(days=1, hours=1),
        status=BookingStatus.CONFIRMED,
    )

    keyboard = admin_booking_actions_keyboard(booking)
    texts = [button.text for row in keyboard.inline_keyboard for button in row]
    callbacks = [button.callback_data for row in keyboard.inline_keyboard for button in row]

    assert "Отменить" in texts
    assert "Отклонить" not in texts
    assert f"adm:cancel:{booking.id}" in callbacks
