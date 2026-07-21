from datetime import UTC, datetime, timedelta

import pytest

from app.core.booking import BookingRecord, BookingStatus, MeetingType, UserProfile
from app.integrations.email import UserEmailNotifier
from app.integrations.email.notifier import SmtpUserEmailSender
from app.settings.config import Settings

NOW = datetime(2026, 7, 21, 10, 0, tzinfo=UTC)


class FakeStore:
    def __init__(self, user: UserProfile, meeting_type: MeetingType) -> None:
        self.user = user
        self.meeting_type = meeting_type

    async def get(self, entity_id):
        if entity_id == self.user.id:
            return self.user
        if entity_id == self.meeting_type.id:
            return self.meeting_type
        return None


class FakeSender:
    def __init__(self) -> None:
        self.messages = []

    async def send(self, *, to_email: str, subject: str, body: str) -> None:
        self.messages.append({"to_email": to_email, "subject": subject, "body": body})


@pytest.mark.asyncio
async def test_user_email_notifier_sends_confirmation_to_user_only() -> None:
    user = UserProfile(telegram_id=1001, full_name="Ирина", email="client@example.com")
    meeting_type = MeetingType(name="Диагностика", allowed_durations_minutes=(60,))
    booking = BookingRecord(
        user_id=user.id,
        meeting_type_id=meeting_type.id,
        duration_minutes=60,
        starts_at=NOW + timedelta(days=2),
        ends_at=NOW + timedelta(days=2, hours=1),
        status=BookingStatus.CONFIRMED,
        display_number=25,
        meeting_url="https://meet.example.com/session",
        user_comment="Тест",
    )
    sender = FakeSender()

    await UserEmailNotifier(
        settings=Settings(),
        store=FakeStore(user, meeting_type),
        sender=sender,
    ).booking_confirmed(booking)

    assert len(sender.messages) == 1
    message = sender.messages[0]
    assert message["to_email"] == "client@example.com"
    assert "№25" in message["subject"]
    assert "Ваша встреча подтверждена." in message["body"]
    assert "Диагностика" in message["body"]
    assert "https://meet.example.com/session" in message["body"]


@pytest.mark.asyncio
async def test_user_email_notifier_does_not_raise_when_smtp_is_not_configured() -> None:
    user = UserProfile(telegram_id=1001, full_name="Ирина", email="client@example.com")
    meeting_type = MeetingType(name="Диагностика", allowed_durations_minutes=(60,))
    booking = BookingRecord(
        user_id=user.id,
        meeting_type_id=meeting_type.id,
        duration_minutes=60,
        starts_at=NOW + timedelta(days=2),
        ends_at=NOW + timedelta(days=2, hours=1),
        status=BookingStatus.CONFIRMED,
        display_number=25,
    )

    await UserEmailNotifier(
        settings=Settings(),
        store=FakeStore(user, meeting_type),
        sender=SmtpUserEmailSender(settings=Settings()),
    ).booking_confirmed(booking)
