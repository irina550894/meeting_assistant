from datetime import UTC, datetime, timedelta

import pytest

from app.core.admin_flow import AdminConfirmationResult, AdminFlowError, AdminFlowService
from app.core.booking import BookingService, BookingStatus, MeetingType

NOW = datetime(2026, 7, 9, 12, 0, tzinfo=UTC)


def consultation() -> MeetingType:
    return MeetingType(name="Консультация", allowed_durations_minutes=(30, 60, 90))


def booking_service() -> BookingService:
    return BookingService()


def admin_flow() -> AdminFlowService:
    return AdminFlowService(booking_service=booking_service())


def consented_user():
    service = booking_service()
    user = service.create_or_update_user(
        telegram_id=1001,
        telegram_username="client",
        now=NOW,
    )
    user.full_name = "Ирина"
    user.email = "irina@example.com"
    service.accept_personal_data_consent(
        user,
        consent_url="https://example.com/consent",
        policy_url="https://example.com/policy",
        now=NOW,
    )
    return user


def pending_booking(user=None):
    user = user or consented_user()
    meeting_type = consultation()
    return booking_service().create_booking(
        user=user,
        meeting_type=meeting_type,
        duration_minutes=60,
        starts_at=NOW + timedelta(days=2),
        ends_at=NOW + timedelta(days=2, hours=1),
        now=NOW,
        existing_bookings=[],
        final_confirmation=True,
    ).booking


def test_admin_access_requires_configured_admin_id() -> None:
    with pytest.raises(AdminFlowError) as error:
        admin_flow().ensure_admin(telegram_id=777, configured_admin_id=None)

    assert error.value.code == "admin_not_configured"


def test_admin_access_rejects_non_admin() -> None:
    with pytest.raises(AdminFlowError) as error:
        admin_flow().ensure_admin(telegram_id=999, configured_admin_id=777)

    assert error.value.code == "admin_access_denied"


def test_admin_access_accepts_configured_admin() -> None:
    admin_flow().ensure_admin(telegram_id=777, configured_admin_id=777)


def test_confirm_booking_uses_calendar_confirmation_result() -> None:
    booking = pending_booking()

    audit = admin_flow().confirm_booking(
        booking=booking,
        confirmation=AdminConfirmationResult(
            google_calendar_event_id="event-1",
            meeting_url="https://meet.example.com/1",
        ),
        now=NOW,
        admin_telegram_id=777,
    )

    assert booking.status == BookingStatus.CONFIRMED
    assert booking.google_calendar_event_id == "event-1"
    assert booking.meeting_url == "https://meet.example.com/1"
    assert audit.action == "booking_confirmed"


def test_reject_booking_saves_reason_and_releases_reservation() -> None:
    booking = pending_booking()

    audit = admin_flow().reject_booking(
        booking=booking,
        now=NOW,
        admin_telegram_id=777,
        reason="Не подходит формат",
    )

    assert booking.status == BookingStatus.REJECTED
    assert booking.rejection_reason == "Не подходит формат"
    assert booking.reservation is not None
    assert booking.reservation.released_at == NOW
    assert audit.action == "booking_rejected"


def test_cancel_confirmed_booking_by_admin_respects_deadline() -> None:
    booking = pending_booking()
    admin_flow().confirm_booking(
        booking=booking,
        confirmation=AdminConfirmationResult(
            google_calendar_event_id="event-1",
            meeting_url="https://meet.example.com/1",
        ),
        now=NOW,
        admin_telegram_id=777,
    )

    audit = admin_flow().cancel_booking(
        booking=booking,
        now=NOW + timedelta(hours=1),
        admin_telegram_id=777,
        reason="Неактуально",
    )

    assert booking.status == BookingStatus.CANCELLED_BY_USER
    assert booking.cancellation_reason == "Неактуально"
    assert audit.action == "booking_cancelled_by_admin"


def test_block_user_closes_active_bookings() -> None:
    user = consented_user()
    booking = pending_booking(user=user)

    result = admin_flow().block_user(
        user=user,
        active_bookings=[booking],
        now=NOW,
        admin_telegram_id=777,
    )

    assert user.is_blocked is True
    assert result.closed_bookings == [booking]
    assert booking.status == BookingStatus.CLOSED_BY_BLOCK


def test_unblock_user_allows_future_booking_attempts() -> None:
    user = consented_user()
    user.is_blocked = True

    audit = admin_flow().unblock_user(user=user, now=NOW, admin_telegram_id=777)

    assert user.is_blocked is False
    assert audit.action == "user_unblocked"


def test_admin_message_audit_does_not_store_message_text() -> None:
    user = consented_user()

    audit = admin_flow().message_sent_audit(
        user_id=user.id,
        now=NOW,
        admin_telegram_id=777,
    )

    assert audit.action == "admin_message_sent"
    assert "message" not in audit.payload
