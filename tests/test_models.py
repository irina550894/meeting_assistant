from app.persistence.models import Base

EXPECTED_TABLES = {
    "audit_logs",
    "background_jobs",
    "bookings",
    "google_oauth_tokens",
    "meeting_types",
    "mini_app_events",
    "mini_app_sessions",
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
    assert "created_source" in booking.columns
    assert "reserved_until" in booking.columns
    assert "google_calendar_event_id" in booking.columns
    assert "previous_booking_id" in booking.columns


def test_mini_app_session_table_has_auth_fields() -> None:
    session = Base.metadata.tables["mini_app_sessions"]

    assert "user_id" in session.columns
    assert "session_hash" in session.columns
    assert "telegram_auth_date" in session.columns
    assert "expires_at" in session.columns
    assert "revoked_at" in session.columns


def test_audit_log_table_has_source() -> None:
    audit_log = Base.metadata.tables["audit_logs"]

    assert "source" in audit_log.columns


def test_mini_app_event_table_has_analytics_fields() -> None:
    event = Base.metadata.tables["mini_app_events"]

    assert "user_id" in event.columns
    assert "event_name" in event.columns
    assert "source" in event.columns
    assert "payload" in event.columns


def test_meeting_type_supports_duration_rules() -> None:
    meeting_type = Base.metadata.tables["meeting_types"]

    assert "allowed_durations_minutes" in meeting_type.columns
    assert "is_fixed_duration" in meeting_type.columns
