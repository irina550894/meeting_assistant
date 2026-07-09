import re
from collections.abc import Iterable
from datetime import date, datetime, timedelta

from app.core.booking import (
    BookingCreationResult,
    BookingRecord,
    BookingService,
    MeetingType,
    UserProfile,
)
from app.core.scheduling import AvailableSlot, ScheduleSettings, SlotCalculationService
from app.core.user_flow.entities import BookingDraft, FlowScheduleContext
from app.core.user_flow.errors import UserFlowError
from app.logging.config import get_logger

logger = get_logger(__name__)

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class UserFlowService:
    def __init__(
        self,
        *,
        booking_service: BookingService | None = None,
        slot_service: SlotCalculationService | None = None,
    ) -> None:
        self.booking_service = booking_service or BookingService()
        self.slot_service = slot_service or SlotCalculationService()

    def validate_email(self, value: str) -> str:
        email = value.strip()
        if not EMAIL_RE.fullmatch(email):
            logger.warning("Email validation failed", extra={"event": "email_validation_failed"})
            raise UserFlowError("invalid_email", "Email is invalid.")
        return email

    def accept_consent(
        self,
        *,
        user: UserProfile,
        personal_data_checked: bool,
        policy_checked: bool,
        consent_url: str | None,
        policy_url: str | None,
        now: datetime,
    ):
        if not personal_data_checked or not policy_checked:
            raise UserFlowError(
                "consent_checkboxes_required",
                "Both consent checkboxes must be selected.",
            )
        if not consent_url or not policy_url:
            raise UserFlowError(
                "consent_urls_required",
                "Consent and policy URLs must be configured.",
            )
        return self.booking_service.accept_personal_data_consent(
            user,
            consent_url=consent_url,
            policy_url=policy_url,
            now=now,
        )

    def ensure_can_start_booking(
        self,
        *,
        user: UserProfile,
        existing_bookings: Iterable[BookingRecord],
    ) -> None:
        self.booking_service.ensure_user_can_start_booking(
            user=user,
            existing_bookings=existing_bookings,
        )

    def available_dates(self, *, now: datetime, settings: ScheduleSettings) -> list[date]:
        start = now.date() + timedelta(days=settings.min_booking_lead_days)
        return [start + timedelta(days=offset) for offset in range(settings.booking_horizon_days)]

    def public_slots(
        self,
        *,
        target_date: date,
        meeting_type: MeetingType,
        duration_minutes: int,
        now: datetime,
        schedule: FlowScheduleContext,
    ) -> list[AvailableSlot]:
        result = self.slot_service.calculate_slots(
            target_date=target_date,
            meeting_type=meeting_type,
            duration_minutes=duration_minutes,
            now=now,
            settings=schedule.settings,
            working_hours=schedule.working_hours,
            restrictions=schedule.restrictions,
            busy_intervals=schedule.busy_intervals,
        )
        return result.public_slots

    def create_booking_from_draft(
        self,
        *,
        user: UserProfile,
        draft: BookingDraft,
        meeting_type: MeetingType,
        now: datetime,
        existing_bookings: Iterable[BookingRecord],
        previous_booking: BookingRecord | None = None,
    ) -> BookingCreationResult:
        self._ensure_draft_complete(draft)

        full_name = draft.full_name.strip() if draft.full_name else user.full_name
        email = self.validate_email(draft.email or "")

        result = self.booking_service.create_booking(
            user=user,
            meeting_type=meeting_type,
            duration_minutes=draft.duration_minutes or 0,
            starts_at=draft.starts_at,
            ends_at=draft.ends_at,
            now=now,
            existing_bookings=existing_bookings,
            final_confirmation=True,
            user_comment=draft.user_comment,
            previous_booking=previous_booking,
        )
        user.full_name = full_name
        user.email = email
        user.updated_at = now
        logger.info(
            "User flow completed with booking creation",
            extra={
                "event": "user_flow_booking_created",
                "booking_id": str(result.booking.id),
                "user_id": str(user.id),
            },
        )
        return result

    def _ensure_draft_complete(self, draft: BookingDraft) -> None:
        missing: list[str] = []
        if not draft.full_name:
            missing.append("full_name")
        if not draft.email:
            missing.append("email")
        if not draft.meeting_type_id:
            missing.append("meeting_type_id")
        if draft.duration_minutes is None:
            missing.append("duration_minutes")
        if draft.starts_at is None:
            missing.append("starts_at")
        if draft.ends_at is None:
            missing.append("ends_at")

        if missing:
            raise UserFlowError("incomplete_booking_draft", ", ".join(missing))
