from datetime import UTC, datetime, timedelta

import pytest

from app.core.booking import BookingService, BookingStatus, BusinessRuleError, MeetingType


NOW = datetime(2026, 7, 9, 12, 0, tzinfo=UTC)


def consultation() -> MeetingType:
    return MeetingType(name="Консультация", allowed_durations_minutes=(30, 60, 90))


def service() -> BookingService:
    return BookingService()


def consented_user():
    user = service().create_or_update_user(
        telegram_id=1001,
        telegram_username="client",
        now=NOW,
    )
    service().accept_personal_data_consent(
        user,
        consent_url="https://example.com/consent",
        policy_url="https://example.com/policy",
        now=NOW,
    )
    return user


def create_pending_booking(user=None, existing_bookings=None):
    user = user or consented_user()
    existing_bookings = existing_bookings or []
    return service().create_booking(
        user=user,
        meeting_type=consultation(),
        duration_minutes=60,
        starts_at=NOW + timedelta(days=2),
        ends_at=NOW + timedelta(days=2, hours=1),
        now=NOW,
        existing_bookings=existing_bookings,
        final_confirmation=True,
    ).booking


def test_cannot_create_booking_without_consent() -> None:
    user = service().create_or_update_user(
        telegram_id=1001,
        telegram_username=None,
        now=NOW,
    )

    with pytest.raises(BusinessRuleError) as error:
        service().create_booking(
            user=user,
            meeting_type=consultation(),
            duration_minutes=60,
            starts_at=NOW + timedelta(days=2),
            ends_at=NOW + timedelta(days=2, hours=1),
            now=NOW,
            existing_bookings=[],
            final_confirmation=True,
        )

    assert error.value.rule == "personal_data_consent_required"


def test_cannot_create_booking_for_blocked_user() -> None:
    user = consented_user()
    user.is_blocked = True

    with pytest.raises(BusinessRuleError) as error:
        service().create_booking(
            user=user,
            meeting_type=consultation(),
            duration_minutes=60,
            starts_at=NOW + timedelta(days=2),
            ends_at=NOW + timedelta(days=2, hours=1),
            now=NOW,
            existing_bookings=[],
            final_confirmation=True,
        )

    assert error.value.rule == "user_blocked"


def test_cannot_create_third_active_booking() -> None:
    user = consented_user()
    active_1 = create_pending_booking(user=user)
    active_2 = create_pending_booking(user=user)

    with pytest.raises(BusinessRuleError) as error:
        service().create_booking(
            user=user,
            meeting_type=consultation(),
            duration_minutes=60,
            starts_at=NOW + timedelta(days=3),
            ends_at=NOW + timedelta(days=3, hours=1),
            now=NOW,
            existing_bookings=[active_1, active_2],
            final_confirmation=True,
        )

    assert error.value.rule == "max_active_bookings"


def test_booking_creates_48_hour_reservation() -> None:
    result = service().create_booking(
        user=consented_user(),
        meeting_type=consultation(),
        duration_minutes=60,
        starts_at=NOW + timedelta(days=2),
        ends_at=NOW + timedelta(days=2, hours=1),
        now=NOW,
        existing_bookings=[],
        final_confirmation=True,
    )

    assert result.booking.status == BookingStatus.PENDING
    assert result.booking.reserved_until == NOW + timedelta(hours=48)
    assert result.reservation.expires_at == NOW + timedelta(hours=48)
    assert result.reservation.is_active is True


def test_cancel_pending_booking_releases_reservation() -> None:
    booking = create_pending_booking()

    service().cancel_booking_by_user(booking, now=NOW + timedelta(hours=1))

    assert booking.status == BookingStatus.CANCELLED_BY_USER
    assert booking.reservation is not None
    assert booking.reservation.released_at == NOW + timedelta(hours=1)


def test_block_user_closes_active_bookings() -> None:
    user = consented_user()
    booking = create_pending_booking(user=user)

    result = service().block_user(user, active_bookings=[booking], now=NOW)

    assert result.user.is_blocked is True
    assert result.closed_bookings == [booking]
    assert booking.status == BookingStatus.CLOSED_BY_BLOCK
    assert booking.reservation is not None
    assert booking.reservation.released_at == NOW


def test_reschedule_creates_new_booking_and_links_previous() -> None:
    user = consented_user()
    old_booking = create_pending_booking(user=user)
    service().confirm_booking(
        old_booking,
        google_calendar_event_id="event-1",
        meeting_url="https://meet.example.com/1",
        now=NOW,
    )

    result = service().create_booking(
        user=user,
        meeting_type=consultation(),
        duration_minutes=60,
        starts_at=NOW + timedelta(days=3),
        ends_at=NOW + timedelta(days=3, hours=1),
        now=NOW + timedelta(hours=1),
        existing_bookings=[],
        final_confirmation=True,
        previous_booking=old_booking,
    )

    assert old_booking.status == BookingStatus.RESCHEDULE_REQUESTED
    assert result.booking.is_reschedule_request is True
    assert result.booking.previous_booking_id == old_booking.id
