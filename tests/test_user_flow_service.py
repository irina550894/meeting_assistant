from datetime import UTC, datetime, timedelta

import pytest

from app.core.booking import BookingService, BusinessRuleError, MeetingType
from app.core.user_flow import BookingDraft, UserFlowError, UserFlowService

NOW = datetime(2026, 7, 9, 12, 0, tzinfo=UTC)


def consultation() -> MeetingType:
    return MeetingType(name="Консультация", allowed_durations_minutes=(30, 60, 90))


def booking_service() -> BookingService:
    return BookingService()


def flow() -> UserFlowService:
    return UserFlowService(booking_service=booking_service(), check_email_deliverability=False)


def consented_user():
    service = booking_service()
    user = service.create_or_update_user(
        telegram_id=1001,
        telegram_username="client",
        now=NOW,
    )
    service.accept_personal_data_consent(
        user,
        consent_url="https://example.com/consent",
        policy_url="https://example.com/policy",
        now=NOW,
    )
    return user


def complete_draft(meeting_type: MeetingType) -> BookingDraft:
    starts_at = NOW + timedelta(days=2)
    return BookingDraft(
        full_name="Ирина",
        email="irina@example.com",
        meeting_type_id=meeting_type.id,
        duration_minutes=60,
        selected_date=starts_at.date(),
        starts_at=starts_at,
        ends_at=starts_at + timedelta(hours=1),
        user_comment="Обсудить проект",
    )


def test_consent_requires_both_checkboxes() -> None:
    user = booking_service().create_or_update_user(
        telegram_id=1001,
        telegram_username=None,
        now=NOW,
    )

    with pytest.raises(UserFlowError) as error:
        flow().accept_consent(
            user=user,
            personal_data_checked=True,
            policy_checked=False,
            consent_url="https://example.com/consent",
            policy_url="https://example.com/policy",
            now=NOW,
        )

    assert error.value.code == "consent_checkboxes_required"
    assert user.has_personal_data_consent is False


def test_consent_requires_document_urls() -> None:
    user = booking_service().create_or_update_user(
        telegram_id=1001,
        telegram_username=None,
        now=NOW,
    )

    with pytest.raises(UserFlowError) as error:
        flow().accept_consent(
            user=user,
            personal_data_checked=True,
            policy_checked=True,
            consent_url=None,
            policy_url="https://example.com/policy",
            now=NOW,
        )

    assert error.value.code == "consent_urls_required"


def test_email_validation_rejects_invalid_email() -> None:
    with pytest.raises(UserFlowError) as error:
        flow().validate_email("not-an-email")

    assert error.value.code == "invalid_email"


def test_email_validation_rejects_domain_without_deliverability() -> None:
    service = UserFlowService(
        booking_service=booking_service(),
        check_email_deliverability=True,
    )

    with pytest.raises(UserFlowError) as error:
        service.validate_email("client@example.com")

    assert error.value.code == "invalid_email"


def test_start_booking_uses_booking_service_business_rules() -> None:
    user = booking_service().create_or_update_user(
        telegram_id=1001,
        telegram_username=None,
        now=NOW,
    )

    with pytest.raises(BusinessRuleError) as error:
        flow().ensure_can_start_booking(user=user, existing_bookings=[])

    assert error.value.rule == "personal_data_consent_required"


def test_create_booking_from_complete_draft_updates_user_and_creates_pending_booking() -> None:
    meeting_type = consultation()
    user = consented_user()

    result = flow().create_booking_from_draft(
        user=user,
        draft=complete_draft(meeting_type),
        meeting_type=meeting_type,
        now=NOW,
        existing_bookings=[],
    )

    assert user.full_name == "Ирина"
    assert user.email == "irina@example.com"
    assert result.booking.user_id == user.id
    assert result.booking.user_comment == "Обсудить проект"
    assert result.reservation.is_active is True


def test_incomplete_draft_does_not_create_booking() -> None:
    meeting_type = consultation()
    user = consented_user()
    draft = complete_draft(meeting_type)
    draft.starts_at = None

    with pytest.raises(UserFlowError) as error:
        flow().create_booking_from_draft(
            user=user,
            draft=draft,
            meeting_type=meeting_type,
            now=NOW,
            existing_bookings=[],
        )

    assert error.value.code == "incomplete_booking_draft"
