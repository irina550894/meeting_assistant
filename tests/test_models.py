from app.persistence.models import Base


EXPECTED_TABLES = {
    "audit_logs",
    "background_jobs",
    "bookings",
    "google_oauth_tokens",
    "meeting_types",
    "notification_logs",
    "schedule_restrictions",
    "schedule_settings",
    "slot_reservations",
    "users",
    "working_hours",
}


def test_metadata_contains_required_tables() -> None:
    assert EXPECTED_TABLES.issubset(set(Base.metadata.tables))


def test_booking_table_has_status_and_reservation_fields() -> None:
    booking = Base.metadata.tables["bookings"]

    assert "status" in booking.columns
    assert "reserved_until" in booking.columns
    assert "google_calendar_event_id" in booking.columns
    assert "previous_booking_id" in booking.columns


def test_meeting_type_supports_duration_rules() -> None:
    meeting_type = Base.metadata.tables["meeting_types"]

    assert "allowed_durations_minutes" in meeting_type.columns
    assert "is_fixed_duration" in meeting_type.columns
