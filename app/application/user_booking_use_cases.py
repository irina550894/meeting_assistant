from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import date, datetime
from uuid import UUID

from app.application.sources import ActionSource
from app.core.booking import BookingRecord, BookingService, MeetingType, UserProfile
from app.core.booking.errors import BusinessRuleError
from app.core.scheduling import AvailableSlot
from app.core.user_flow import BookingDraft, UserFlowError, UserFlowService
from app.integrations.google_calendar import GoogleCalendarError
from app.integrations.telegram.ports import (
    BackgroundJobSchedulerPort,
    BookingStore,
    CalendarEventGateway,
    MeetingTypeStore,
    ScheduleProvider,
    UserFlowNotifier,
    UserStore,
)
from app.logging.config import get_logger
from app.settings.config import Settings

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class UserBookingUseCaseDeps:
    settings: Settings
    users: UserStore
    meeting_types: MeetingTypeStore
    bookings: BookingStore
    schedule: ScheduleProvider
    flow: UserFlowService
    booking_service: BookingService
    clock: Callable[[], datetime]
    notifier: UserFlowNotifier | None = None
    calendar_events: CalendarEventGateway | None = None
    background_jobs: BackgroundJobSchedulerPort | None = None


class UserBookingUseCases:
    def __init__(self, deps: UserBookingUseCaseDeps) -> None:
        self.deps = deps

    async def accept_consent(self, user: UserProfile) -> UserProfile:
        audit = self.deps.flow.accept_consent(
            user=user,
            personal_data_checked=True,
            policy_checked=True,
            consent_url=self.deps.settings.personal_data_consent_url,
            policy_url=self.deps.settings.personal_data_policy_url,
            now=self.deps.clock(),
        )
        audit = _with_mini_app_source(audit)
        await self.deps.users.save(user)
        await self.deps.bookings.save_audit_entries([audit])
        return user

    async def list_meeting_types(self) -> list[MeetingType]:
        return await self.deps.meeting_types.list_active()

    async def available_dates(self) -> list[date]:
        schedule = await self.deps.schedule.context_for_date(self.deps.clock().date())
        return self.deps.flow.available_dates(now=self.deps.clock(), settings=schedule.settings)

    async def available_slots(
        self,
        *,
        target_date: date,
        meeting_type_id: UUID,
        duration_minutes: int,
    ) -> list[AvailableSlot]:
        meeting_type = await self.deps.meeting_types.get(meeting_type_id)
        if meeting_type is None:
            raise UserFlowError("meeting_type_not_found", "Meeting type was not found.")
        schedule = await self.deps.schedule.context_for_date(target_date)
        return self.deps.flow.public_slots(
            target_date=target_date,
            meeting_type=meeting_type,
            duration_minutes=duration_minutes,
            now=self.deps.clock(),
            schedule=schedule,
        )

    async def create_booking(
        self,
        *,
        user: UserProfile,
        draft: BookingDraft,
    ) -> BookingRecord:
        meeting_type = await self._meeting_type_for_draft(draft)
        previous_booking = await self._previous_booking_for_draft(draft, user)
        result = self.deps.flow.create_booking_from_draft(
            user=user,
            draft=draft,
            meeting_type=meeting_type,
            now=self.deps.clock(),
            existing_bookings=await self.deps.bookings.list_by_user(user.id),
            previous_booking=previous_booking,
        )
        result.booking.created_source = ActionSource.MINI_APP.value
        result.audit_entries[:] = [_with_mini_app_source(audit) for audit in result.audit_entries]
        await self.deps.users.save(user)
        await self.deps.bookings.save_booking_result(result)
        if self.deps.background_jobs:
            await self.deps.background_jobs.schedule_booking_created(
                result.booking,
                now=result.booking.created_at or self.deps.clock(),
            )
        if self.deps.notifier:
            if result.booking.is_reschedule_request:
                await self.deps.notifier.reschedule_requested(result.booking)
            else:
                await self.deps.notifier.booking_created(result.booking)
        return result.booking

    async def list_user_bookings(self, user: UserProfile) -> list[BookingRecord]:
        return await self.deps.bookings.list_by_user(user.id)

    async def get_user_booking(self, *, user: UserProfile, booking_id: UUID) -> BookingRecord:
        booking = await self.deps.bookings.get_for_user(booking_id, user.id)
        if booking is None:
            raise BusinessRuleError("booking_not_found", "Booking was not found.")
        return booking

    async def cancel_user_booking(
        self,
        *,
        user: UserProfile,
        booking_id: UUID,
        reason: str | None = None,
    ) -> BookingRecord:
        booking = await self.get_user_booking(user=user, booking_id=booking_id)
        audit = self.deps.booking_service.cancel_booking_by_user(
            booking,
            now=self.deps.clock(),
            reason=reason,
        )
        audit = _with_mini_app_source(audit)
        await self.deps.bookings.save_booking(booking)
        await self.deps.bookings.save_audit_entries([audit])
        if self.deps.calendar_events and booking.google_calendar_event_id:
            try:
                await self.deps.calendar_events.cancel_event(booking.google_calendar_event_id)
            except GoogleCalendarError as error:
                logger.warning(
                    "Google Calendar event cancellation failed",
                    extra={
                        "event": "google_api_error",
                        "operation": "miniapp_cancel_event",
                        "booking_id": str(booking.id),
                        "error_code": error.code,
                        "error_type": type(error).__name__,
                    },
                )
        if self.deps.notifier:
            await self.deps.notifier.booking_cancelled_by_user(booking)
        return booking

    async def prepare_reschedule(self, *, user: UserProfile, booking_id: UUID) -> BookingRecord:
        return await self.get_user_booking(user=user, booking_id=booking_id)

    async def _meeting_type_for_draft(self, draft: BookingDraft) -> MeetingType:
        if not draft.meeting_type_id:
            raise UserFlowError("meeting_type_required", "Meeting type is required.")
        meeting_type = await self.deps.meeting_types.get(draft.meeting_type_id)
        if meeting_type is None:
            raise UserFlowError("meeting_type_not_found", "Meeting type was not found.")
        return meeting_type

    async def _previous_booking_for_draft(
        self,
        draft: BookingDraft,
        user: UserProfile,
    ) -> BookingRecord | None:
        if not draft.previous_booking_id:
            return None
        previous_booking = await self.deps.bookings.get_for_user(draft.previous_booking_id, user.id)
        if previous_booking is None:
            raise BusinessRuleError("previous_booking_not_found", "Previous booking was not found.")
        return previous_booking


def _with_mini_app_source(audit):
    return replace(audit, source=ActionSource.MINI_APP.value)
