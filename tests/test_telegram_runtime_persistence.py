from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.core.booking import BookingStatus
from app.persistence.models import Booking, MeetingType, SlotReservation, User
from app.persistence.repositories.telegram_runtime import (
    _booking_record,
    _default_working_hours_rules,
    _mark_previous_booking_reschedule_requested,
    _meeting_type,
    _reservation_record,
    _user_profile,
)


def test_runtime_store_maps_user_model_to_profile() -> None:
    user_id = uuid4()
    now = datetime(2026, 7, 11, 10, 0, tzinfo=UTC)
    user = User(
        id=user_id,
        telegram_id=123,
        telegram_username="client",
        full_name="Client Name",
        email="client@example.com",
        is_blocked=True,
        created_at=now,
        updated_at=now,
        consent_accepted_at=now,
        consent_url="https://example.com/consent",
        policy_url="https://example.com/policy",
    )

    profile = _user_profile(user)

    assert profile.id == user_id
    assert profile.telegram_id == 123
    assert profile.is_blocked is True
    assert profile.has_personal_data_consent is True


def test_runtime_store_maps_booking_with_reservation() -> None:
    booking_id = uuid4()
    user_id = uuid4()
    meeting_type_id = uuid4()
    starts_at = datetime(2026, 7, 13, 10, 0, tzinfo=UTC)
    reservation = SlotReservation(
        id=uuid4(),
        booking_id=booking_id,
        starts_at=starts_at,
        ends_at=starts_at + timedelta(hours=1),
        expires_at=starts_at - timedelta(hours=2),
    )
    booking = Booking(
        id=booking_id,
        user_id=user_id,
        meeting_type_id=meeting_type_id,
        duration_minutes=60,
        starts_at=starts_at,
        ends_at=starts_at + timedelta(hours=1),
        status=BookingStatus.PENDING.value,
        reserved_until=starts_at - timedelta(hours=2),
        reservation=reservation,
    )

    record = _booking_record(booking)

    assert record.id == booking_id
    assert record.status == BookingStatus.PENDING
    assert record.reservation is not None
    assert record.reservation.booking_id == booking_id


def test_runtime_store_maps_meeting_type_duration_rules() -> None:
    meeting_type = MeetingType(
        id=uuid4(),
        name="Consultation",
        slug="consultation",
        allowed_durations_minutes=[30, 60, 90],
        is_fixed_duration=False,
        is_active=True,
    )

    record = _meeting_type(meeting_type)

    assert record.allowed_durations_minutes == (30, 60, 90)
    assert record.is_active is True


def test_runtime_store_maps_reservation_model() -> None:
    booking_id = uuid4()
    starts_at = datetime(2026, 7, 13, 10, 0, tzinfo=UTC)
    reservation = SlotReservation(
        id=uuid4(),
        booking_id=booking_id,
        starts_at=starts_at,
        ends_at=starts_at + timedelta(hours=1),
        expires_at=starts_at - timedelta(hours=2),
        released_at=starts_at - timedelta(hours=1),
    )

    record = _reservation_record(reservation)

    assert record.booking_id == booking_id
    assert record.is_active is False


def test_default_working_hours_match_local_memory_rules() -> None:
    rules = _default_working_hours_rules()

    assert len(rules) == 7
    assert [rule.weekday for rule in rules] == list(range(7))
    assert [rule.is_working_day for rule in rules] == [
        True,
        True,
        True,
        True,
        True,
        False,
        False,
    ]


async def test_reschedule_result_updates_previous_booking_status() -> None:
    booking = Booking(
        id=uuid4(),
        user_id=uuid4(),
        meeting_type_id=uuid4(),
        duration_minutes=60,
        starts_at=datetime(2026, 7, 13, 10, 0, tzinfo=UTC),
        ends_at=datetime(2026, 7, 13, 11, 0, tzinfo=UTC),
        status=BookingStatus.CONFIRMED.value,
    )
    now = datetime(2026, 7, 11, 10, 0, tzinfo=UTC)

    class FakeSession:
        async def get(self, model, entity_id):
            assert model is Booking
            assert entity_id == booking.id
            return booking

    await _mark_previous_booking_reschedule_requested(FakeSession(), booking.id, now=now)

    assert booking.status == BookingStatus.RESCHEDULE_REQUESTED.value
    assert booking.updated_at == now
